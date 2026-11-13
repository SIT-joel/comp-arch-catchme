import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api, Interaction, Me, Reading, Session } from "../api";
import { buildSegments, formatDuration, GraphPoint } from "../graph";

const WINDOW_S = 60;

function HeartGraph({ readings, selfId }: { readings: Reading[]; selfId: string }) {
  const nowSec = useMemo(() => {
    const last = readings[readings.length - 1];
    return last ? new Date(last.captured_at).getTime() / 1000 : Date.now() / 1000;
  }, [readings]);

  const series = useMemo(() => {
    const byUser = new Map<string, GraphPoint[]>();
    for (const r of readings) {
      const t = new Date(r.captured_at).getTime() / 1000;
      if (t < nowSec - WINDOW_S) continue;
      const list = byUser.get(r.user_id) ?? [];
      list.push({
        t: t - (nowSec - WINDOW_S),
        bpm: r.heart_rate.bpm ?? 0,
        valid: r.heart_rate.valid,
        status: r.heart_rate.status,
      });
      byUser.set(r.user_id, list);
    }
    return byUser;
  }, [readings, nowSec]);

  const width = 720;
  const height = 180;
  const yFor = (bpm: number) => height - ((Math.min(Math.max(bpm, 40), 180) - 40) / 140) * (height - 20) - 10;
  const xFor = (t: number) => (t / WINDOW_S) * width;

  const colors = ["#e0559b", "#4f8ef7"];

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="hr-graph" role="img" aria-label="Live heart rate">
      <rect x={0} y={0} width={width} height={height} fill="#141826" rx={8} />
      {[60, 100, 140].map((bpm) => (
        <g key={bpm}>
          <line x1={0} x2={width} y1={yFor(bpm)} y2={yFor(bpm)} stroke="#2a3050" strokeDasharray="4 4" />
          <text x={4} y={yFor(bpm) - 3} fill="#5a6382" fontSize={10}>
            {bpm}
          </text>
        </g>
      ))}
      {[...series.entries()].map(([userId, points]) => {
        const color = userId === selfId ? colors[0] : colors[1];
        return buildSegments(points).map((seg, i) => (
          <polyline
            key={`${userId}-${i}`}
            fill="none"
            stroke={color}
            strokeWidth={2}
            points={seg.points.map((p) => `${xFor(p.t)},${yFor(p.bpm)}`).join(" ")}
          />
        ));
      })}
      {series.size === 0 && (
        <text x={width / 2} y={height / 2} fill="#5a6382" fontSize={13} textAnchor="middle">
          no readings yet — waiting for wearable telemetry
        </text>
      )}
    </svg>
  );
}

function statusLabel(r: Reading): string {
  if (r.heart_rate.valid) return `♥ ${r.heart_rate.bpm} BPM`;
  switch (r.heart_rate.status) {
    case "no_contact":
      return "no contact";
    case "warming_up":
      return "warming up";
    case "invalid_signal":
      return "invalid signal";
    default:
      return "no reading";
  }
}

export default function SessionPage({ me, refreshMe }: { me: Me; refreshMe: () => Promise<void> }) {
  const { id } = useParams<{ id: string }>();
  const [session, setSession] = useState<Session | null>(null);
  const [interaction, setInteraction] = useState<Interaction | null>(null);
  const [interactionError, setInteractionError] = useState<string | null>(null);
  const [readings, setReadings] = useState<Reading[]>([]);
  const [pinInput, setPinInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    if (!id) return;
    try {
      const [s, r] = await Promise.all([api.getSession(id), api.readings(id)]);
      setSession(s);
      setReadings(r.readings);
      try {
        setInteraction(await api.interaction(id));
        setInteractionError(null);
      } catch (err) {
        // Historical sessions and invitations before both users accept have
        // no v1 interaction record.
        setInteraction(null);
        const expectsInteraction = s.state === "active" &&
          (s.quest_id === "together" || s.quest_id === "heart_challenge");
        setInteractionError(expectsInteraction
          ? (err instanceof Error ? err.message : "Quest interaction state is unavailable.")
          : null);
      }
      if (s.state === "completed" || s.state === "cancelled") await refreshMe();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load session");
    }
  }, [id, refreshMe]);

  useEffect(() => {
    void refresh();
    const sse = new EventSource("/api/v1/events", { withCredentials: true });
    const onState = () => void refresh();
    sse.addEventListener("state", onState);
    sse.addEventListener("hello", onState);
    timerRef.current = window.setInterval(onState, 3000); // snapshot reload per contract
    return () => {
      sse.close();
      if (timerRef.current) window.clearInterval(timerRef.current);
    };
  }, [refresh]);

  if (error) return <main className="page"><div className="error">{error}</div></main>;
  if (!session) return <main className="page">Loading…</main>;

  const meParticipant = session.participants.find((p) => p.user_id === me.user.id);
  const partner = session.participants.find((p) => p.user_id !== me.user.id);
  const isCreator = session.created_by === me.user.id;
  const latestSelf = [...readings].reverse().find((r) => r.is_self);
  const latestPartner = [...readings].reverse().find((r) => !r.is_self);

  const doAccept = async () => {
    try {
      await api.acceptSession(session.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to accept");
    }
  };

  const doCancel = async () => {
    try {
      await api.cancelSession(session.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel");
    }
  };

  const runInteraction = async (action: () => Promise<Interaction>) => {
    setError(null);
    try {
      setInteraction(await action());
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Interaction failed");
      await refresh();
    }
  };

  const sendPin = () => {
    if (!id || !interaction?.stage || interaction.partner_code_version === null || !/^\d{4}$/.test(pinInput)) return;
    void runInteraction(() => api.submitPin(id, interaction.stage!, pinInput, interaction.partner_code_version!));
    setPinInput("");
  };

  const title = session.quest_id === "heart_challenge" ? "Keep Your Cool" :
    session.quest_id === "together" ? "Together Time" : "Outdoor Visit";
  const baseline = (interaction?.results.baseline ?? {}) as Record<string, number>;
  const rounds = (interaction?.results.rounds ?? {}) as Record<string, Record<string, number>>;
  const bpmChanges = (interaction?.results.bpm_changes ?? {}) as Record<string, number[]>;

  return (
    <main className="page">
      {session.demo && <div className="demo-banner">DEMO MODE — this session uses shortened durations.</div>}
      <section className="card">
        <h2>
          {title} · {session.state}
          {session.demo && <span className="tag demo-tag">demo</span>}
        </h2>
        <div className="progress-row">
          <progress max={session.target_ms ?? 1} value={session.progress_ms} />
          <span>
            {formatDuration(session.progress_ms)} /{" "}
            {session.target_ms ? formatDuration(session.target_ms) : "not active yet"}
          </span>
        </div>
        <p className="muted">
          Participants: {session.participants.map((p) => `${p.display_name}${p.accepted ? "" : " (invited)"}`).join(", ")}
        </p>
        {interactionError && <div className="error" role="alert">Quest PIN state unavailable: {interactionError}</div>}
        {session.state === "pending" && !meParticipant?.accepted && (
          <button onClick={doAccept}>Accept this quest</button>
        )}
        {(session.state === "pending" || session.state === "active") && (
          <button className="danger" onClick={doCancel}>
            Cancel session
          </button>
        )}
        {session.state === "completed" && (
          <div className="success">
            Completed! Each participant earned 100 points and 100 XP. {isCreator ? "You created this session." : ""}
          </div>
        )}
        {session.state === "cancelled" && <div className="muted">Cancelled — incomplete progress was not awarded.</div>}
      </section>

      {interaction && (session.state === "active" || session.state === "completed") && (
        <section className="card quest-interaction">
          <h2>{title} interaction</h2>
          {session.quest_id === "together" && (interaction.phase === "start_pin" || interaction.phase === "end_pin") && (
            <>
              <p className="muted">
                {interaction.phase === "start_pin"
                  ? "Ask your partner for the code shown on their TinyScreen+, then enter it here. Both people must exchange codes before the timer starts."
                  : "Time complete. Exchange the new codes with your partner to finish and receive the reward."}
              </p>
              <div className="pin-panel">
                <div>
                  <strong>Your code</strong>
                  <div className="pin-code">{interaction.own_code ?? "----"}</div>
                  <div className="muted small">
                    {interaction.own_code_confirmed_by_partner ? "Partner entered your code" : "Waiting for partner to enter your code"}
                  </div>
                  {interaction.own_code_expires_at && (
                    <div className="muted small">Expires {new Date(interaction.own_code_expires_at).toLocaleTimeString()}</div>
                  )}
                  {interaction.stage && (
                    <button className="secondary" onClick={() => void runInteraction(() => api.refreshPin(session.id, interaction.stage!))}>
                      Refresh my code
                    </button>
                  )}
                </div>
                <div>
                  <strong>Enter your partner’s code</strong>
                  <input
                    className="pin-input"
                    type="text"
                    inputMode="numeric"
                    autoComplete="off"
                    maxLength={4}
                    pattern="[0-9]{4}"
                    aria-label="Partner four digit code"
                    value={pinInput}
                    onChange={(event) => setPinInput(event.target.value.replace(/\D/g, "").slice(0, 4))}
                    placeholder="0000"
                  />
                  <button disabled={pinInput.length !== 4 || interaction.partner_code_version === null}
                    onClick={sendPin}>Confirm code</button>
                  <div className="muted small">
                    {interaction.partner_code_confirmed_by_me ? "You confirmed your partner’s code" : "Not confirmed yet"}
                  </div>
                </div>
              </div>
              <p className="muted small">Codes expire after five minutes. A refresh invalidates the old code. PIN exchange is a game step, not proof of identity or proximity.</p>
            </>
          )}

          {session.quest_id === "together" && interaction.phase === "timing" && (
            <p>Codes exchanged. Verified Bluetooth presence is counting; gaps pause the timer.</p>
          )}

          {session.quest_id === "heart_challenge" && (
            <>
              {/* v2: heart quest removed — legacy sessions render read-only. */}
              <p className="muted">Keep Your Cool (removed quest) — historical session. 10-second baseline plus two 10-second turns with live heart rate.</p>
              <p><strong>Phase:</strong> {interaction.phase.replace("_", " ")} · round {Math.min(interaction.round_index, 2)} of 2</p>
              {(Object.keys(baseline).length > 0 || Object.keys(rounds).length > 0) && (
                <div className="heart-results">
                  <strong>Measured heart-rate changes</strong>
                  {Object.entries(baseline).map(([userId, bpm]) => {
                    const roundVals = Object.entries(rounds).map(([round, values], index) => {
                      const change = bpmChanges[userId]?.[index];
                      const signed = change === undefined ? "" : ` (${change >= 0 ? "+" : ""}${change} BPM)`;
                      return `${round}: ${values[userId] ?? "—"} BPM${signed}`;
                    });
                    return <p key={userId}>{userId === me.user.id ? "You" : partner?.display_name ?? "Partner"}: baseline {bpm} BPM · {roundVals.join(" · ")}</p>;
                  })}
                  <span className="muted small">These are sensor readings only, not a lie or attraction score.</span>
                </div>
              )}
            </>
          )}

          {session.quest_id === "raid" && (
            <p className="muted">
              {session.landmark ? `Landmark: ${session.landmark.name}. ` : ""}
              {session.state === "completed"
                ? session.raid_outcome === "win"
                  ? "Raid won — the boss fell."
                  : "Raid lost — the boss survived."
                : "The fight runs board-to-board on the wearables; both boards report their outcome here when it ends."}
            </p>
          )}
        </section>
      )}

      <section className="card">
        <h2>{session.quest_id === "heart_challenge" ? "Keep Your Cool · live heart rate" : "Live heart rate"}</h2>
        <p className="muted small">
          Pink = you, blue = {partner?.display_name ?? "partner"}. Gaps mean missing or invalid readings — they are
          never interpolated. Heart rate is a playful sensor value, not a measure of attraction.
        </p>
        <HeartGraph readings={readings} selfId={me.user.id} />
        <div className="row gap">
          <div className={`sensor-chip ${latestSelf?.heart_rate.valid ? "ok" : "bad"}`}>
            you: {latestSelf ? statusLabel(latestSelf) : "no data"}
          </div>
          <div className={`sensor-chip ${latestPartner?.heart_rate.valid ? "ok" : "bad"}`}>
            partner: {latestPartner ? statusLabel(latestPartner) : "no data"}
          </div>
        </div>
      </section>
    </main>
  );
}
