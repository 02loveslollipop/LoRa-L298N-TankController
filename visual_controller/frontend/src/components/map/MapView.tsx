import { useEffect, useMemo, useState } from "react";
import { MapContainer, Marker, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { GpsSnapshot } from "../../state/useTankStore";
import "./MapView.css";

// Fix for default marker icon
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";

delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
});

const customMarkerIcon = new L.Icon({
  iconUrl:
    "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-blue.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowUrl: markerShadow,
  shadowSize: [41, 41]
});

interface MapViewProps {
  gps?: GpsSnapshot | null;
}

function MapPositionUpdater({ gps }: { gps?: GpsSnapshot | null }) {
  const map = useMap();

  useEffect(() => {
    if (!gps) return;
    const center: L.LatLngExpression = [gps.lat, gps.lon];
    map.setView(center, map.getZoom() < 15 ? 15 : map.getZoom(), { animate: true });
  }, [gps, map]);

  return null;
}

export function MapView({ gps }: MapViewProps) {
  const [tileError, setTileError] = useState(false);

  const position = useMemo<L.LatLngExpression>(() => {
    if (gps && Number.isFinite(gps.lat) && Number.isFinite(gps.lon)) {
      return [gps.lat, gps.lon] as L.LatLngExpression;
    }
    return [0, 0];
  }, [gps]);

  const hasFix = Boolean(gps && Number.isFinite(gps.lat) && Number.isFinite(gps.lon));

  return (
    <div className="map-card card">
      <div className="section-title">Position</div>
      <MapContainer center={position} zoom={hasFix ? 16 : 2} zoomControl={false} className="tank-map">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a> contributors'
          url={
            tileError
              ? "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png"
              : "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          }
          eventHandlers={{
            tileerror: () => setTileError(true)
          }}
        />
        {hasFix && (
          <Marker position={position} icon={customMarkerIcon}>
            <span>Tank</span>
          </Marker>
        )}
        <MapPositionUpdater gps={gps ?? undefined} />
      </MapContainer>
      <div className="map-meta">
        {hasFix ? (
          <>
            <span>
              Lat: {gps?.lat.toFixed(6)} Lon: {gps?.lon.toFixed(6)}
            </span>
            <span>Alt: {gps?.alt_m?.toFixed(1) ?? "—"} m</span>
            <span>Speed: {gps?.speed_mps?.toFixed(2) ?? "—"} m/s</span>
            <span>HDOP: {gps?.hdop?.toFixed(1) ?? "—"}</span>
            <span>Sat: {gps?.satellites ?? "—"}</span>
          </>
        ) : (
          <span>No GPS fix received yet.</span>
        )}
      </div>
    </div>
  );
}
