import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, Landmark, Me, Quest, Session } from "../api";
import { formatDuration } from "../graph";

function useSse(onChange: () => void) {
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  useEffect(() => {
    const source = new EventSource("/api/v1/events", { withCredentials: true });
    source.addEventListener("state", () => onChangeRef.current());
    source.onerror = () => {
      // Reconnect logic is native; on reconnect the hello event triggers a refresh.
      source.addEventListener("hello", () => onChangeRef.current());
    };
    return () => source.close();
  }, []);
}

function questName(id: Session["quest_id"]): string {
  if (id === "together") return "Together Time";
  if (id === "explore") return "Outdoor Visit";
  if (id === "raid") return "Landmark Raid";
  if (id === "quiz") return "Know Your Partner";
  return "Keep Your Cool (removed)"; // legacy sessions only
}

const SPECIES_LABEL: Record<string, string> = { spark: "Spark", fluff: "Fluff", pip: "Pip" };
const STAGE_LABEL: Record<number, string> = { 1: "baby", 2: "teen", 3: "adult" };

export default function DashboardPage({ me, refreshMe }: { me: Me; refreshMe: () => Promise<void> }) {
  const [quests, setQuests] = useState<Quest[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [landmarks, setLandmarks] = useState<Landmark[]>([]);
  const [landmarkId, setLandmarkId] = useState<string>("");
  const [demoMode, setDemoMode] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const refresh = useCallback(async () => {
    const [q, s, l] = await Promise.all([api.quests(), api.listSessions(), api.landmarks()]);
    setQuests(q.quests);
    setSessions(s.sessions);
    setLandmarks(l.landmarks);
    await refreshMe();
  }, [refreshMe]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useSse(() => void refresh());

  const current = sessions.find((s) => s.state === "pending" || s.state === "active");
  const history = sessions.filter((s) => s.state === "completed" || s.state === "cancelled").slice(0, 10);

  const startQuest = async (questId: string) => {
    setError(null);
    setMessage(null);
    try {
      const created = await api.createSession(
        questId,
        demoMode,
        questId === "raid" ? landmarkId || undefined : undefined,
      );
      setMessage("Invitation sent — waiting for your partner to accept.");
      navigate(`/sessions/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start quest");
    }
  };

  const acceptCurrent = async () => {
    if (!current) return;
    setError(null);
    try {
      await api.acceptSession(current.id);
      navigate(`/sessions/${current.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to accept");
    }
  };

  const cancelCurrent = async () => {
    if (!current) return;
    setError(null);
    try {
      await api.cancelSession(current.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel");
    }
  };

  const meAccepted = current?.participants.find((p) => p.user_id === me.user.id)?.accepted ?? false;
  const partner = me.partner;

  return (
    <main className="page">
      {demoMode && (
        <div className="demo-banner">DEMO MODE — shortened quest durations; demo sessions are recorded as demo.</div>
      )}

      <section className="cards">
        <div className="card">
          <h2>{me.user.display_name}</h2>
          <div className="big">Level {me.user.level}</div>
          <div className="muted">
            {me.user.points} points · {me.user.lifetime_xp} lifetime XP
          </div>
        </div>
        <div className="card">
          <h2>Partner</h2>
          {partner ? (
            <>
              <div className="big">{partner.display_name}</div>
              <div className="muted">
                Level {partner.level} · location sharing {partner.location_sharing ? "on" : "off"}
              </div>
            </>
          ) : (
            <div className="muted">No partner configured.</div>
          )}
        </div>
        <div className="card">
          <h2>Wearable</h2>
          {me.device ? (
            <>
              <div className="big">{me.device.name}</div>
              <div className="muted">Alias {me.device.firmware_alias} · bound to this account</div>
            </>
          ) : (
            <div className="warning">No wearable bound yet — bind it in the Android app.</div>
          )}
        </div>
        <div className="card">
          <h2>Pet</h2>
          {me.pet?.species ? (
            <>
              <div className="big">
                {me.pet.name ?? SPECIES_LABEL[me.pet.species]}{" "}
                <span className="muted small">
                  {SPECIES_LABEL[me.pet.species]} · {STAGE_LABEL[me.pet.evolution_stage]}
                </span>
              </div>
              <div className="muted">
                Level {me.pet.level} · care streak {me.pet.care_streak} day
                {me.pet.care_streak === 1 ? "" : "s"} ·{" "}
                {me.pet.cared_today ? "cared for today ✓" : "not cared for today"}
              </div>
            </>
          ) : (
            <div className="muted">No pet yet — bond with one on your TinyScreen+.</div>
          )}
        </div>
      </section>

      {current && (
        <section className="card current-session">
          <h2>
            {current.state === "pending" ? "Invitation" : "Active quest"}: {questName(current.quest_id)}
            {current.demo && <span className="tag demo-tag">demo</span>}
          </h2>
          <div className="progress-row">
            <progress max={current.target_ms ?? 1} value={current.progress_ms} />
            <span>
              {formatDuration(current.progress_ms)} / {current.target_ms ? formatDuration(current.target_ms) : "—"}
            </span>
          </div>
          <div className="row gap">
            {!meAccepted && current.state === "pending" && <button onClick={acceptCurrent}>Accept</button>}
            <Link className="button" to={`/sessions/${current.id}`}>
              Open live view
            </Link>
            <button className="danger" onClick={cancelCurrent}>
              Cancel
            </button>
          </div>
        </section>
      )}

      {message && <div className="info">{message}</div>}
      {error && <div className="error">{error}</div>}

      <section className="card">
        <h2>Start a quest</h2>
        <label className="check-row">
          <input type="checkbox" checked={demoMode} onChange={(e) => setDemoMode(e.target.checked)} />
          Demo mode (short durations, prominently recorded)
        </label>
        <div className="quest-grid">
          {quests.map((q) => (
            <div key={q.quest_id} className="quest-tile">
              <h3>{q.name}</h3>
              <p className="muted">{q.description}</p>
              <p className="muted small">
                {formatDuration(demoMode ? q.demo_duration_ms : q.normal_duration_ms)} · evidence: {q.evidence}
              </p>
              {q.quest_id === "explore" && !q.geofence_configured && (
                <p className="warning">Geofence not configured on the server — explore cannot start yet.</p>
              )}
              {q.quest_id === "raid" && (
                <label className="check-row">
                  Landmark:{" "}
                  <select value={landmarkId} onChange={(e) => setLandmarkId(e.target.value)}>
                    <option value="">Choose…</option>
                    {landmarks.map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <button
                disabled={
                  !!current ||
                  (q.quest_id === "explore" && !q.geofence_configured) ||
                  (q.quest_id === "raid" && !landmarkId)
                }
                onClick={() => startQuest(q.quest_id)}
              >
                Invite partner
              </button>
            </div>
          ))}
        </div>
      </section>

      <section className="card">
        <h2>Recent sessions</h2>
        {history.length === 0 && <div className="muted">No completed sessions yet.</div>}
        <table>
          <thead>
            <tr>
              <th>Quest</th>
              <th>State</th>
              <th>Progress</th>
              <th>When</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {history.map((s) => (
              <tr key={s.id}>
                <td>
                  {questName(s.quest_id)}
                  {s.demo && <span className="tag demo-tag">demo</span>}
                </td>
                <td>{s.state}</td>
                <td>
                  {formatDuration(s.progress_ms)}
                  {s.target_ms ? ` / ${formatDuration(s.target_ms)}` : ""}
                </td>
                <td>{new Date(s.created_at).toLocaleString()}</td>
                <td>
                  <Link to={`/sessions/${s.id}`}>view</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}
