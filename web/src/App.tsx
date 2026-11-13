import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, Me } from "./api";
import DashboardPage from "./pages/DashboardPage";
import DiscoveryPage from "./pages/DiscoveryPage";
import LoginPage from "./pages/LoginPage";
import SessionPage from "./pages/SessionPage";
import ShopPage from "./pages/ShopPage";
import TransactionsPage from "./pages/TransactionsPage";

export default function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  const refreshMe = useCallback(async () => {
    try {
      setMe(await api.me());
    } catch {
      setMe(null);
    } finally {
      setAuthReady(true);
    }
  }, []);

  useEffect(() => {
    void refreshMe();
  }, [refreshMe]);

  const logout = async () => {
    try {
      await api.logout();
    } finally {
      setMe(null);
      navigate("/");
    }
  };

  if (!authReady) {
    return <div className="center-page">Loading…</div>;
  }

  if (!me) {
    return <LoginPage onLoggedIn={refreshMe} />;
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link to="/" className="brand">
          Catch Me
        </Link>
        <nav>
          <Link to="/" className={location.pathname === "/" ? "active" : ""}>
            Dashboard
          </Link>
          <Link to="/discovery" className={location.pathname.startsWith("/discovery") ? "active" : ""}>
            Discovery
          </Link>
          <Link to="/shop" className={location.pathname.startsWith("/shop") ? "active" : ""}>
            Shop
          </Link>
          <Link to="/transactions" className={location.pathname.startsWith("/transactions") ? "active" : ""}>
            History
          </Link>
        </nav>
        <div className="user-chip">
          <span>
            {me.user.display_name} · Lv {me.user.level} · {me.user.points} pts
          </span>
          <button onClick={logout}>Sign out</button>
        </div>
      </header>
      <Routes>
        <Route path="/" element={<DashboardPage me={me} refreshMe={refreshMe} />} />
        <Route path="/discovery" element={<DiscoveryPage me={me} refreshMe={refreshMe} />} />
        <Route path="/sessions/:id" element={<SessionPage me={me} refreshMe={refreshMe} />} />
        <Route path="/shop" element={<ShopPage me={me} refreshMe={refreshMe} />} />
        <Route path="/transactions" element={<TransactionsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}
