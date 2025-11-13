import { NavLink } from "react-router-dom";
import { useTankContext } from "../App";
import "./TopNav.css";

export function TopNav() {
  const { tankId, setTankId } = useTankContext();

  return (
    <header className="top-nav">
      <div className="top-nav__brand">
        <div className="top-nav__title">Tank Operations Console</div>
        <div className="top-nav__subtitle">nene.02labs.me</div>
      </div>
      <nav className="top-nav__links">
        <NavLink to="/legacy" className={({ isActive }) => (isActive ? "active" : "")}>
          Legacy Controller
        </NavLink>
        <NavLink to="/nt" className={({ isActive }) => (isActive ? "active" : "")}>
          NT Controller
        </NavLink>
        <NavLink to="/joycon" className={({ isActive }) => (isActive ? "active" : "")}>
          Joy-Con Controller
        </NavLink>
        <NavLink to="/status" className={({ isActive }) => (isActive ? "active" : "")}>
          Tank Status
        </NavLink>
      </nav>
      <div className="top-nav__tank">
        <label htmlFor="tank-selector">Tank ID</label>
        <input
          id="tank-selector"
          value={tankId}
          onChange={(event) => setTankId(event.target.value.trim())}
          spellCheck={false}
        />
      </div>
    </header>
  );
}
