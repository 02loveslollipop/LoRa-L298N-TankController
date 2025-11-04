import { useState } from "react";
import { sendCommand } from "../../utils/api";
import "./ManualButtons.css";

interface ManualButtonsProps {
  tankId: string;
}

const COMMANDS = [
  { label: "Forward", command: "forward" },
  { label: "Stop", command: "stop", intent: "danger" },
  { label: "Backward", command: "backward" },
  { label: "Left", command: "left" },
  { label: "Right", command: "right" }
];

export function ManualButtons({ tankId }: ManualButtonsProps) {
  const [speed, setSpeed] = useState<number>(180);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastCommand, setLastCommand] = useState<string | null>(null);

  async function handleCommand(command: string) {
    setBusy(true);
    setError(null);
    try {
      await sendCommand(tankId, {
        command,
        leftSpeed: speed,
        rightSpeed: speed
      });
      setLastCommand(command);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send command");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card manual-card">
      <div className="section-title">Manual Control</div>
      <div className="manual-grid">
        {COMMANDS.map(({ label, command, intent }) => (
          <button
            key={command}
            className={`btn ${intent === "danger" ? "secondary danger" : ""}`}
            disabled={busy}
            onClick={() => handleCommand(command)}
          >
            {label}
          </button>
        ))}
      </div>
      <label className="manual-speed">
        <span>Speed ({speed})</span>
        <input
          type="range"
          min={0}
          max={255}
          value={speed}
          onChange={(event) => setSpeed(Number(event.target.value))}
        />
      </label>
      <div className="manual-footer">
        <span className="muted">Last command: {lastCommand ?? "—"}</span>
        {error && <span className="error">{error}</span>}
      </div>
    </div>
  );
}
