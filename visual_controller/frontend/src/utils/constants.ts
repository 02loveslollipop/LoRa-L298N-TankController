export const apiBaseUrl =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || window.location.origin;

export const wsBaseUrl =
  import.meta.env.VITE_WS_BASE_URL?.replace(/\/$/, "") ||
  (window.location.protocol === "https:" ? `wss://${window.location.host}` : `ws://${window.location.host}`);

export const defaultTankId = import.meta.env.VITE_DEFAULT_TANK_ID || "tank_001";
