import { useEffect, useMemo, useState } from "react";
import { resetTank, fetchTanks, TankSnapshot } from "../utils/api";
import { useTankContext } from "../App";
import "./Status.css";

interface TankEntry {
  id: string;
  data: TankSnapshot[string];
}

export function StatusPage() {
  const { tankId, setTankId } = useTankContext();
  const [snapshot, setSnapshot] = useState<TankSnapshot>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);

  async function load(announce = false) {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchTanks();
      setSnapshot(data);
      setLastUpdated(Date.now());
    } catch (err) {
      if (announce) {
        setError(err instanceof Error ? err.message : "Failed to load tanks");
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const id = window.setInterval(() => load(), 30000);
    return () => window.clearInterval(id);
  }, []);

  const entries = useMemo<TankEntry[]>(() => {
    return Object.entries(snapshot)
      .map(([id, data]) => ({ id, data }))
      .sort((a, b) => a.id.localeCompare(b.id));
  }, [snapshot]);

  async function handleReset(id: string) {
    try {
      await resetTank(id);
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reset tank");
    }
  }

  return (
    <div className="status-layout">
      <div className="card status-controls">
        <div className="section-title">Fleet Overview</div>
        <div className="status-toolbar">
          <button className="btn" onClick={() => load(true)} disabled={loading}>
            Refresh
          </button>
          <span className="muted">Last updated: {lastUpdated ? new Date(lastUpdated).toLocaleTimeString() : "—"}</span>
        </div>
        {error && <div className="error">{error}</div>}
      </div>
      <div className="status-grid">
        {entries.length === 0 && <div className="card">No tanks reported yet.</div>}
        {entries.map(({ id, data }) => {
          const connection = (data.connection ?? {}) as Record<string, unknown>;
          const telemetry = (data.payload ?? {}) as Record<string, unknown>;
          const connected = connection.connected === true;
          const lastSeen = (connection.lastSeen as string | undefined) ?? (telemetry.receivedAt as string | undefined);
          const commandsSent = connection.commandsSent as number | undefined;

          return (
            <div key={id} className={`card status-card ${id === tankId ? "active" : ""}`}>
              <div className="status-card__header">
                <div>
                  <div className="status-card__id">{id}</div>
                  <div className={`status-card__badge ${connected ? "online" : "offline"}`}>
                    {connected ? "Connected" : "Disconnected"}
                  </div>
                </div>
                <button className="btn secondary" onClick={() => setTankId(id)}>
                  Control
                </button>
              </div>
              <div className="status-card__meta">
                <span>Commands: {commandsSent ?? "—"}</span>
                <span>Last seen: {lastSeen ? new Date(lastSeen).toLocaleString() : "Unknown"}</span>
              </div>
              <pre>{JSON.stringify({ connection, telemetry }, null, 2)}</pre>
              <div className="status-card__actions">
                <button className="btn secondary" onClick={() => handleReset(id)}>
                  Reset tank
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
