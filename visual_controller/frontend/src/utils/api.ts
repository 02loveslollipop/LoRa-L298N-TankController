import axios from "axios";
import { apiBaseUrl } from "./constants";

export interface CommandPayload {
  command: string;
  leftSpeed?: number;
  rightSpeed?: number;
  sequence?: number;
  timestamp?: string;
}

export async function sendCommand(tankId: string, payload: CommandPayload) {
  const url = `${apiBaseUrl}/command/${encodeURIComponent(tankId)}`;
  const body = {
    ...payload,
    timestamp: payload.timestamp ?? new Date().toISOString()
  };
  await axios.post(url, body, {
    headers: { "Content-Type": "application/json" }
  });
}

export interface TankSnapshot {
  [tankId: string]: {
    connection?: Record<string, unknown>;
    payload?: Record<string, unknown>;
    radar?: Record<string, unknown>;
    [key: string]: unknown;
  };
}

export async function fetchTanks(): Promise<TankSnapshot> {
  const url = `${apiBaseUrl}/tanks`;
  const response = await axios.get<TankSnapshot>(url, { headers: { "Cache-Control": "no-cache" } });
  return response.data;
}

export async function resetTank(tankId: string) {
  const url = `${apiBaseUrl}/tanks/${encodeURIComponent(tankId)}/reset`;
  await axios.post(url);
}
