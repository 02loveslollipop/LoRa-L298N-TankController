import { useMemo } from "react";
import { ManualButtons } from "../components/control/ManualButtons";
import { MapView } from "../components/map/MapView";
import { RadarCanvas } from "../components/radar/RadarCanvas";
import { useTankSocket } from "../hooks/useTankSocket";
import { useTankStore } from "../state/useTankStore";
import { useTankContext } from "../App";
import "./LegacyController.css";

export function LegacyControllerPage() {
  const { tankId } = useTankContext();
  const telemetry = useTankStore((state) => state.telemetry);
  const radar = useTankStore((state) => state.radar);
  const gps = useTankStore((state) => state.gps);

  useTankSocket({ tankId });

  const telemetryDisplay = useMemo(
    () =>
      telemetry
        ? JSON.stringify(
            {
              ...telemetry,
              payload: telemetry.payload
            },
            null,
            2
          )
        : "Awaiting telemetry…",
    [telemetry]
  );

  return (
    <div className="legacy-layout">
      <div className="legacy-left">
        <RadarCanvas reading={radar} />
        <MapView gps={gps} />
        <div className="card telemetry-card">
          <div className="section-title">Telemetry</div>
          <pre>{telemetryDisplay}</pre>
        </div>
      </div>
      <div className="legacy-right">
        <ManualButtons tankId={tankId} />
      </div>
    </div>
  );
}
