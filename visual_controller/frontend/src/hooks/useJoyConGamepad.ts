import { useEffect, useMemo, useState } from "react";

const JOYCON_REGEX = /(joy[-\s]?con|nintendo|pro controller)/i;

export interface JoyConSnapshot {
  supported: boolean;
  connected: boolean;
  id?: string;
  axes: number[];
  buttons: { pressed: boolean; touched: boolean; value: number }[];
  timestamp: number;
}

const initialSupported = typeof window !== "undefined" && "getGamepads" in navigator;

const initialState: JoyConSnapshot = {
  supported: initialSupported,
  connected: false,
  id: undefined,
  axes: [],
  buttons: [],
  timestamp: 0
};

/**
 * Polls the Gamepad API for any connected Nintendo Joy-Con or Switch Pro controller
 * and exposes a normalized snapshot. The hook only re-renders ~12 times per second
 * to avoid thrashing the UI.
 */
export function useJoyConGamepad(pollIntervalMs = 80): JoyConSnapshot {
  const [state, setState] = useState<JoyConSnapshot>(initialState);

  const supported = useMemo(
    () => typeof window !== "undefined" && typeof navigator !== "undefined" && "getGamepads" in navigator,
    []
  );

  useEffect(() => {
    if (!supported) {
      setState((prev) => ({ ...prev, supported: false, connected: false }));
      return;
    }

    let cancelled = false;
    let timer: number | undefined;

    const poll = () => {
      if (cancelled) {
        return;
      }
      const pads = navigator.getGamepads ? Array.from(navigator.getGamepads()) : [];
      const preferred =
        pads.find((pad) => pad && /joy[-\s]?con \(l\/r\)/i.test(pad.id)) ??
        pads.find((pad) => pad && /pro controller/i.test(pad.id)) ??
        pads.find((pad) => pad && JOYCON_REGEX.test(pad.id));

      if (preferred) {
        setState({
          supported: true,
          connected: true,
          id: preferred.id,
          timestamp: preferred.timestamp ?? performance.now(),
          axes: preferred.axes ? [...preferred.axes] : [],
          buttons: preferred.buttons.map((button) => ({
            pressed: button.pressed,
            touched: button.touched,
            value: button.value
          }))
        });
      } else {
        setState((prev) => ({
          supported: true,
          connected: false,
          id: undefined,
          axes: [],
          buttons: [],
          timestamp: performance.now()
        }));
      }

      timer = window.setTimeout(poll, pollIntervalMs);
    };

    timer = window.setTimeout(poll, pollIntervalMs);

    const handleConnected = () => poll();
    const handleDisconnected = () => poll();

    window.addEventListener("gamepadconnected", handleConnected);
    window.addEventListener("gamepaddisconnected", handleDisconnected);

    return () => {
      cancelled = true;
      if (timer) {
        window.clearTimeout(timer);
      }
      window.removeEventListener("gamepadconnected", handleConnected);
      window.removeEventListener("gamepaddisconnected", handleDisconnected);
    };
  }, [supported, pollIntervalMs]);

  return state;
}

