import { useEffect, useRef, useState } from "react";
import { RadarMessage } from "../../state/useTankStore";
import "./RadarCanvas.css";

interface RadarCanvasProps {
  reading?: RadarMessage;
  width?: number;
  height?: number;
}

interface RadarCell {
  angle: number;
  distance: number;
  at: number;
}

export function RadarCanvas({ reading, width = 360, height = 360 }: RadarCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [angleStep, setAngleStep] = useState<number>(3);
  const [maxDistance, setMaxDistance] = useState<number>(120);
  const cellsRef = useRef<RadarCell[]>(new Array(61).fill(null));

  useEffect(() => {
    if (!reading) {
      return;
    }

    if (typeof reading.step_deg === "number" && reading.step_deg > 0) {
      const nextStep = Math.max(1, Math.min(15, Math.round(reading.step_deg)));
      if (nextStep !== angleStep) {
        setAngleStep(nextStep);
        cellsRef.current = new Array(Math.floor(180 / nextStep) + 1).fill(null);
      }
    }

    if (typeof reading.max_distance_cm === "number" && reading.max_distance_cm > 0) {
      setMaxDistance(Math.min(300, reading.max_distance_cm));
    }

    const angle = Number(reading.angle ?? reading.payload?.angle ?? 0);
    const distance = Number(reading.distance_cm ?? reading.payload?.distance_cm ?? -1);
    const valid = Boolean(reading.valid ?? reading.payload?.valid) && Number.isFinite(distance) && distance >= 0;

    if (Number.isFinite(angle)) {
      const slots = cellsRef.current.length;
      const index = Math.max(0, Math.min(Math.round(angle / angleStep), slots - 1));
      cellsRef.current[index] = valid
        ? {
            angle,
            distance,
            at: Date.now()
          }
        : null;
    }

    drawRadar({ angle, distance, valid });
  }, [reading, angleStep]);

  useEffect(() => {
    drawRadar();
  }, [angleStep, maxDistance]);

  function drawRadar(current?: { angle: number; distance: number; valid: boolean }) {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }

    const radius = canvas.width / 2;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#031024";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.strokeStyle = "#11365a";
    ctx.lineWidth = 1.5;
    const rings = 4;
    for (let i = 1; i <= rings; i += 1) {
      const ringRadius = radius * (i / rings);
      ctx.beginPath();
      ctx.arc(radius, radius, ringRadius, Math.PI, 0);
      ctx.stroke();
    }

    ctx.strokeStyle = "#11365a";
    for (let deg = 0; deg <= 180; deg += 30) {
      const rad = degToRad(deg);
      ctx.beginPath();
      ctx.moveTo(radius, radius);
      ctx.lineTo(radius + Math.cos(rad) * radius, radius - Math.sin(rad) * radius);
      ctx.stroke();
    }

    ctx.save();
    for (const entry of cellsRef.current) {
      if (!entry) continue;
      const entryRad = degToRad(entry.angle);
      const age = Date.now() - entry.at;
      const alpha = Math.max(0.15, 0.55 - age / 4000);
      const entryRadius = Math.max(2, Math.min(entry.distance / maxDistance, 1) * radius);

      ctx.strokeStyle = `rgba(0, 255, 193, ${alpha.toFixed(3)})`;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(radius, radius);
      ctx.lineTo(radius + Math.cos(entryRad) * entryRadius, radius - Math.sin(entryRad) * entryRadius);
      ctx.stroke();
    }
    ctx.restore();

    if (current) {
      const rad = degToRad(current.angle);
      const normalized = current.valid ? Math.max(0, Math.min(current.distance / maxDistance, 1)) : 0;
      const pingRadius = normalized * radius;

      ctx.strokeStyle = "#48f1c9";
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(radius, radius);
      ctx.lineTo(radius + Math.cos(rad) * radius, radius - Math.sin(rad) * radius);
      ctx.stroke();

      if (current.valid) {
        ctx.fillStyle = "#1fffab";
        ctx.beginPath();
        ctx.arc(radius + Math.cos(rad) * pingRadius, radius - Math.sin(rad) * pingRadius, 6, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  return (
    <div className="radar-card card">
      <div className="section-title">Radar Telemetry</div>
      <canvas ref={canvasRef} width={width} height={height} />
      <div className="radar-meta">
        <span>Angle step: {angleStep}°</span>
        <span>Range: {maxDistance.toFixed(0)} cm</span>
      </div>
    </div>
  );
}

function degToRad(angle: number) {
  return Math.PI - (angle * Math.PI) / 180;
}
