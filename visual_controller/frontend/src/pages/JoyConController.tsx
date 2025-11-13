import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MapView } from "../components/map/MapView";
import { RadarCanvas } from "../components/radar/RadarCanvas";
import { useJoyConGamepad } from "../hooks/useJoyConGamepad";
import { useTankSocket } from "../hooks/useTankSocket";
import { useTankStore } from "../state/useTankStore";
import { sendCommand } from "../utils/api";
import { useTankContext } from "../App";
import "./JoyConController.css";

const MAX_SPEED = 255;
const DEAD_ZONE = 0.18;
const TURN_ATTENUATION = 0.65;
const COMMAND_INTERVAL_MS = 150;
const DEFAULT_TURN_SPEED = 150;

type DriveDirection = "forward" | "backward" | "stopped";

interface PendingCommand {
  command: string;
  left: number;
  right: number;
}

function clampSpeed(value: number) {
  return Math.max(0, Math.min(MAX_SPEED, Math.round(value)));
}

export function JoyConControllerPage() {
  const { tankId } = useTankContext();
  const telemetry = useTankStore((state) => state.telemetry);
  const radar = useTankStore((state) => state.radar);
  const gps = useTankStore((state) => state.gps);
  const joyCon = useJoyConGamepad();

  const [showModal, setShowModal] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [driveDirection, setDriveDirection] = useState<DriveDirection>("stopped");
  const [lastCommand, setLastCommand] = useState("stop");
  const [leftSpeed, setLeftSpeed] = useState(0);
  const [rightSpeed, setRightSpeed] = useState(0);

  const inflightRef = useRef(false);
  const lastSentRef = useRef(0);
  const lastPayloadRef = useRef<PendingCommand | null>(null);

  useTankSocket({ tankId, enabled: !showModal });

  const telemetryDisplay = useMemo(
    () => (telemetry ? JSON.stringify(telemetry, null, 2) : "Awaiting telemetry…"),
    [telemetry]
  );

  const issueCommand = useCallback(
    async (payload: PendingCommand) => {
      const now = performance.now();
      const previous = lastPayloadRef.current;
      const dedupe =
        previous &&
        previous.command === payload.command &&
        Math.abs(previous.left - payload.left) < 4 &&
        Math.abs(previous.right - payload.right) < 4 &&
        now - lastSentRef.current < COMMAND_INTERVAL_MS;
      if (dedupe || inflightRef.current) {
        return;
      }

      inflightRef.current = true;
      setBusy(true);
      setError(null);
      try {
        await sendCommand(tankId, {
          command: payload.command,
          leftSpeed: payload.left,
          rightSpeed: payload.right
        });
        lastSentRef.current = performance.now();
        lastPayloadRef.current = payload;
        setLastCommand(payload.command);
        setLeftSpeed(payload.left);
        setRightSpeed(payload.right);
        setDriveDirection((prev) => {
          if (payload.command === "forward") return "forward";
          if (payload.command === "backward") return "backward";
          if (payload.command === "stop") return "stopped";
          return prev;
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to send command");
      } finally {
        inflightRef.current = false;
        setBusy(false);
      }
    },
    [tankId]
  );

  useEffect(() => {
    if (showModal) {
      return;
    }

    if (!joyCon.supported) {
      return;
    }

    if (!joyCon.connected) {
      return;
    }

    const axisY = -(joyCon.axes[1] ?? 0);
    const axisX = joyCon.axes[0] ?? 0;

    const brakePressed =
      joyCon.buttons[0]?.pressed || joyCon.buttons[1]?.pressed || joyCon.buttons[8]?.pressed;
    const dpadLeft = joyCon.buttons[14]?.pressed;
    const dpadRight = joyCon.buttons[15]?.pressed;

    if (brakePressed) {
      void issueCommand({ command: "stop", left: 0, right: 0 });
      return;
    }

    const hasThrottle = Math.abs(axisY) > DEAD_ZONE;
    if (hasThrottle) {
      const direction = axisY > 0 ? "forward" : "backward";
      const baseSpeed = clampSpeed(Math.abs(axisY) * MAX_SPEED);
      let left = baseSpeed;
      let right = baseSpeed;

      const turnMagnitude = Math.abs(axisX) > DEAD_ZONE ? Math.abs(axisX) : 0;
      if (turnMagnitude > 0) {
        const attenuation = Math.min(1, turnMagnitude * TURN_ATTENUATION);
        if (axisX > 0) {
          right = clampSpeed(baseSpeed * (1 - attenuation));
        } else if (axisX < 0) {
          left = clampSpeed(baseSpeed * (1 - attenuation));
        }
      } else if (dpadLeft || dpadRight) {
        const attenuation = 0.55;
        if (dpadRight) {
          right = clampSpeed(baseSpeed * (1 - attenuation));
        }
        if (dpadLeft) {
          left = clampSpeed(baseSpeed * (1 - attenuation));
        }
      }

      void issueCommand({ command: direction, left, right });
      return;
    }

    if (dpadLeft && !dpadRight) {
      void issueCommand({ command: "left", left: DEFAULT_TURN_SPEED, right: DEFAULT_TURN_SPEED });
      return;
    }
    if (dpadRight && !dpadLeft) {
      void issueCommand({ command: "right", left: DEFAULT_TURN_SPEED, right: DEFAULT_TURN_SPEED });
      return;
    }

    if (lastPayloadRef.current?.command !== "stop") {
      void issueCommand({ command: "stop", left: 0, right: 0 });
    }
  }, [joyCon, showModal, issueCommand]);

  useEffect(() => {
    return () => {
      if (lastPayloadRef.current?.command !== "stop") {
        void issueCommand({ command: "stop", left: 0, right: 0 });
      }
    };
  }, [issueCommand]);

  return (
    <div className="joycon-layout">
      {showModal && (
        <div className="joycon-modal-backdrop">
          <div className="joycon-modal card">
            <h2>Nintendo Joy-Con Controller</h2>
            <p>
              Pair the Joy-Con or Switch Pro Controller over Bluetooth, then press any button to
              grant this tab access to the Gamepad API.
            </p>
            <ol>
              <li>Put each Joy-Con in pairing mode (hold the small rail button).</li>
              <li>Connect them in Windows/macOS Bluetooth settings.</li>
              <li>Click below once you see “Connected”.</li>
            </ol>
            <button className="btn primary" onClick={() => setShowModal(false)}>
              Enter controller
            </button>
          </div>
        </div>
      )}
      <div className="joycon-left">
        <div className="card joycon-map-card">
          <MapView gps={gps} />
        </div>
        <div className="card joycon-telemetry">
          <div className="section-title">Telemetry</div>
          <pre>{telemetryDisplay}</pre>
        </div>
      </div>
      <div className="joycon-right">
        <div className="card joycon-radar">
          <RadarCanvas reading={radar} />
        </div>
        <div className="card joycon-status">
          <div className="section-title">Joy-Con Link</div>
          <div className="joycon-status-grid">
            <span>
              Support:{" "}
              <strong>{joyCon.supported ? "Gamepad API detected" : "Unsupported browser"}</strong>
            </span>
            <span>
              Connection:{" "}
              <strong>{joyCon.connected ? "Controller ready" : "No Joy-Con detected"}</strong>
            </span>
            <span>Controller ID: {joyCon.id ?? "—"}</span>
            <span>Last command: {lastCommand}</span>
            <span>Left track: {leftSpeed}</span>
            <span>Right track: {rightSpeed}</span>
            <span>Direction: {driveDirection}</span>
            <span>Status: {busy ? "Sending…" : "Idle"}</span>
          </div>
          {error && <div className="error">{error}</div>}
          <div className="joycon-hints">
            <strong>Controls</strong>
            <ul>
              <li>Left stick up/down – throttle forward/back (analog speed)</li>
              <li>Left stick horizontal or D-Pad – trim turns while moving</li>
              <li>D-Pad left/right while stopped – pivot turns</li>
              <li>B / A / + – emergency stop</li>
            </ul>
            <small>
              Chrome/Edge expose Joy-Con input only after user interaction. If readings appear
              frozen, tap anywhere and press a Joy-Con button again.
            </small>
          </div>
        </div>
      </div>
    </div>
  );
}

