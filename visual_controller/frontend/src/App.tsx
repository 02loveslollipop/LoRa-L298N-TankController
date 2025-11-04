import { createContext, useContext, useMemo, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { TopNav } from "./layout/TopNav";
import { LegacyControllerPage } from "./pages/LegacyController";
import { NtControllerPage } from "./pages/NtController";
import { StatusPage } from "./pages/Status";
import { defaultTankId } from "./utils/constants";

interface TankContextValue {
  tankId: string;
  setTankId: (value: string) => void;
}

const TankContext = createContext<TankContextValue | undefined>(undefined);

export function useTankContext() {
  const value = useContext(TankContext);
  if (!value) {
    throw new Error("useTankContext must be used within a TankProvider");
  }
  return value;
}

export default function App() {
  const [tankId, setTankId] = useState(defaultTankId);

  const value = useMemo<TankContextValue>(() => ({ tankId, setTankId }), [tankId]);

  return (
    <TankContext.Provider value={value}>
      <div className="app-shell">
        <TopNav />
        <main className="app-main">
          <Routes>
            <Route path="/" element={<Navigate to="/legacy" replace />} />
            <Route path="/legacy" element={<LegacyControllerPage />} />
            <Route path="/nt" element={<NtControllerPage />} />
            <Route path="/status" element={<StatusPage />} />
          </Routes>
        </main>
      </div>
    </TankContext.Provider>
  );
}
