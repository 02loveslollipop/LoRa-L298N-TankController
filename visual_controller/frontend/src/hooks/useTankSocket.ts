import { useEffect, useRef } from "react";
import ReconnectingWebSocket from "reconnecting-websocket";
import { useTankStore } from "../state/useTankStore";
import { wsBaseUrl } from "../utils/constants";

interface UseTankSocketOptions {
  tankId: string;
  enabled?: boolean;
}

export function useTankSocket({ tankId, enabled = true }: UseTankSocketOptions) {
  const setTelemetry = useTankStore((state) => state.setTelemetry);
  const setRadar = useTankStore((state) => state.setRadar);
  const reset = useTankStore((state) => state.reset);
  const socketRef = useRef<ReconnectingWebSocket | null>(null);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const wsUrl = `${wsBaseUrl.replace(/^ws/, "ws")}/ws/ui/${encodeURIComponent(tankId)}`;
    const ws = new ReconnectingWebSocket(wsUrl, [], {
      maxReconnectionDelay: 5000,
      minReconnectionDelay: 500,
      connectionTimeout: 4000
    });

    ws.addEventListener("open", () => {
      console.log("[WS] Connected to", wsUrl);
    });

    ws.addEventListener("close", () => {
      console.log("[WS] Disconnected from", wsUrl);
      reset();
    });

    ws.addEventListener("message", (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "telemetry") {
          setTelemetry(data);
        } else if (data.type === "radar") {
          setRadar(data.payload ?? data);
        }
      } catch (err) {
        console.warn("[WS] Failed to parse message", err);
      }
    });

    socketRef.current = ws;

    return () => {
      ws.close();
      socketRef.current = null;
    };
  }, [tankId, enabled, setTelemetry, setRadar, reset]);
}
