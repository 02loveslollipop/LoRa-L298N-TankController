import { create } from "zustand";

export interface TelemetryMessage {
  tankId: string;
  payload?: Record<string, unknown>;
  receivedAt?: string;
  [key: string]: unknown;
}

export interface RadarMessage {
  angle: number;
  distance_cm: number;
  valid: boolean;
  max_distance_cm?: number;
  step_deg?: number;
  [key: string]: unknown;
}

export interface GpsSnapshot {
  lat: number;
  lon: number;
  alt_m?: number;
  speed_mps?: number;
  hdop?: number;
  satellites?: number;
  fix_age_ms?: number;
  timestamp?: number;
}

interface TankStore {
  telemetry?: TelemetryMessage;
  radar?: RadarMessage;
  gps?: GpsSnapshot | null;
  setTelemetry: (message: TelemetryMessage) => void;
  setRadar: (message: RadarMessage) => void;
  setGps: (snapshot: GpsSnapshot | null) => void;
  reset: () => void;
}

export const useTankStore = create<TankStore>((set) => ({
  telemetry: undefined,
  radar: undefined,
  gps: null,
  setTelemetry: (message) => {
    const gps = (message.payload as Record<string, unknown> | undefined)?.gps as
      | Record<string, unknown>
      | null
      | undefined;
    set((prev) => ({
      telemetry: message,
      gps:
        gps && typeof gps.lat === "number" && typeof gps.lon === "number"
          ? {
              lat: gps.lat as number,
              lon: gps.lon as number,
              alt_m: (gps.alt_m as number | undefined) ?? prev.gps?.alt_m,
              speed_mps: (gps.speed_mps as number | undefined) ?? prev.gps?.speed_mps,
              hdop: (gps.hdop as number | undefined) ?? prev.gps?.hdop,
              satellites: (gps.satellites as number | undefined) ?? prev.gps?.satellites,
              fix_age_ms: (gps.fix_age_ms as number | undefined) ?? prev.gps?.fix_age_ms,
              timestamp: Date.now()
            }
          : prev.gps
    }));
  },
  setRadar: (message) => set({ radar: message }),
  setGps: (snapshot) => set({ gps: snapshot }),
  reset: () => set({ telemetry: undefined, radar: undefined, gps: null })
}));
