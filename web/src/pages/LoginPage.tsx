import { FormEvent, useState } from "react";
import { api, ApiError } from "../api";

export default function LoginPage({ onLoggedIn }: { onLoggedIn: () => Promise<void> }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(username, password);
      await onLoggedIn();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Network error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="center-page">
      <form className="login-card" onSubmit={submit}>
        <h1>Catch Me</h1>
        <p className="muted">Sign in with your seeded demo account.</p>
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>
        {error && <div className="error">{error}</div>}
        <button type="submit" disabled={busy || !username || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
