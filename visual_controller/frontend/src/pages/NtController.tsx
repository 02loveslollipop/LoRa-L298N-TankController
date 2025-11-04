import { useEffect, useMemo, useState } from "react";
import { MapView } from "../components/map/MapView";
import { RadarCanvas } from "../components/radar/RadarCanvas";
import { useTankSocket } from "../hooks/useTankSocket";
import { useTankStore } from "../state/useTankStore";
import { sendCommand } from "../utils/api";
import { useTankContext } from "../App";
import "./NtController.css";

const SPEED_STEP = 25;
const DEFAULT_TURN_SPEED = 160;
const MAX_SPEED = 255;

type Direction = "forward" | "backward" | "stopped";
type Turn = "left" | "right" | null;

interface NtState {
  direction: Direction;
  speed: number;
  turn: Turn;
}

export function NtControllerPage() {
  const { tankId } = useTankContext();
  const telemetry = useTankStore((state) => state.telemetry);
  const radar = useTankStore((state) => state.radar);
  const gps = useTankStore((state) => state.gps);

  const [ntState, setNtState] = useState<NtState>({ direction: "stopped", speed: 0, turn: null });
  const [showModal, setShowModal] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useTankSocket({ tankId, enabled: !showModal });

  useEffect(() => {
    if (showModal) {
      return;
    }

    function applyBrake() {
      dispatchCommand("stop", 0);
      setNtState({ direction: "stopped", speed: 0, turn: null });
    }

    function accelerate(direction: Direction) {
      if (direction === "stopped") return;
      setNtState((state) => {
        const sameDirection = state.direction === direction;
        const baseSpeed = sameDirection ? state.speed : 0;
        const nextSpeed = clampSpeed(baseSpeed + SPEED_STEP);
        dispatchCommand(direction, nextSpeed);
        return { direction, speed: nextSpeed, turn: null };
      });
    }

    function startTurn(turn: Exclude<Turn, null>) {
      setNtState((state) => {
        const base = state.speed > 0 ? state.speed : DEFAULT_TURN_SPEED;
        const resultSpeed = clampSpeed(base);
        dispatchCommand(turn, resultSpeed);
        return { ...state, turn, speed: resultSpeed };
      });
    }

    function finishTurn(turn: Exclude<Turn, null>) {
      setNtState((state) => {
        if (state.turn !== turn) {
          return state;
        }
        if (state.direction === "forward" && state.speed > 0) {
          dispatchCommand("forward", state.speed);
        } else if (state.direction === "backward" && state.speed > 0) {
          dispatchCommand("backward", state.speed);
        } else {
          dispatchCommand("stop", 0);
          return { direction: "stopped", speed: 0, turn: null };
        }
        return { ...state, turn: null };
      });
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.repeat) return;
      switch (event.key.toLowerCase()) {
        case "w":
          event.preventDefault();
          accelerate("forward");
          break;
        case "s":
          event.preventDefault();
          accelerate("backward");
          break;
        case "a":
          event.preventDefault();
          startTurn("left");
          break;
        case "d":
          event.preventDefault();
          startTurn("right");
          break;
        case " ":
          event.preventDefault();
          applyBrake();
          break;
        default:
          break;
      }
    }

    function handleKeyUp(event: KeyboardEvent) {
      switch (event.key.toLowerCase()) {
        case "a":
          finishTurn("left");
          break;
        case "d":
          finishTurn("right");
          break;
        default:
          break;
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
      dispatchCommand("stop", 0);
      setNtState({ direction: "stopped", speed: 0, turn: null });
    };
  }, [showModal, tankId]);

  function clampSpeed(value: number) {
    return Math.max(0, Math.min(MAX_SPEED, Math.round(value)));
  }

  async function dispatchCommand(command: string, speed: number) {
    setBusy(true);
    setError(null);
    try {
      await sendCommand(tankId, {
        command,
        leftSpeed: speed,
        rightSpeed: speed,
        timestamp: new Date().toISOString()
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send command");
    } finally {
      setBusy(false);
    }
  }

  const telemetryDisplay = useMemo(
    () => (telemetry ? JSON.stringify(telemetry, null, 2) : "Awaiting telemetry…"),
    [telemetry]
  );

  return (
    <div className="nt-layout">
      {showModal && (
        <div className="nt-modal-backdrop">
          <div className="nt-modal">
            <h2>NT Controller</h2>
            <p>Use the keyboard shortcuts below to drive the tank:</p>
            <ul>
              <li>
                <strong>W</strong> – Accelerate forward
              </li>
              <li>
                <strong>S</strong> – Accelerate reverse
              </li>
              <li>
                <strong>A / D</strong> – Turn left / right
              </li>
              <li>
                <strong>Space</strong> – Immediate brake
              </li>
            </ul>
            <button className="btn" onClick={() => setShowModal(false)}>
              Enter controller
            </button>
          </div>
        </div>
      )}
      <div className="nt-map">
        <MapView gps={gps} />
      </div>
      <div className="nt-right">
        <div className="card nt-radar">
          <RadarCanvas reading={radar} />
        </div>
        <div className="card nt-info">
          <div className="section-title">Controller State</div>
          <div className="nt-status-row">
            <span>Direction: {ntState.direction}</span>
            <span>Speed: {ntState.speed}</span>
            <span>Turn: {ntState.turn ?? "—"}</span>
            <span>Status: {busy ? "Sending…" : "Idle"}</span>
          </div>
          {error && <div className="error">{error}</div>}
          <div className="section-title">Telemetry</div>
          <pre className="nt-telemetry">{telemetryDisplay}</pre>
          <div className="nt-instructions">
            <strong>Tips</strong>
            <span>Hold W/S to maintain motion. Release A/D to exit a turn.</span>
            <span>Use the brake before reversing direction to protect the drivetrain.</span>
          </div>
        </div>
      </div>
    </div>
  );
}
