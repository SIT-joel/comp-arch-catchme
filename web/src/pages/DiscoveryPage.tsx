import { useCallback, useEffect, useState } from "react";
import {
  api,
  DiscoveryProfile,
  DiscoverySnapshot,
  INTEREST_TAGS,
  Invitation,
} from "../api";

/**
 * Nearby discovery (docs/DISCOVERY_PLAN.md): editable profile + opt-ins,
 * 5-second result refresh with honest freshness/age labels, invitations,
 * and partnership display/end. Distances are rounded to 50 m by the server;
 * raw coordinates are never exposed here.
 */
export default function DiscoveryPage({ refreshMe }: { me: unknown; refreshMe: () => void }) {
  const [profile, setProfile] = useState<DiscoveryProfile | null>(null);
  const [snapshot, setSnapshot] = useState<DiscoverySnapshot | null>(null);
  const [invitations, setInvitations] = useState<{ incoming: Invitation[]; outgoing: Invitation[] } | null>(null);
  const [partnered, setPartnered] = useState<boolean | null>(null);
  const [partnerName, setPartnerName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  const refreshStatic = useCallback(async () => {
    try {
      const me = await api.me();
      setPartnered(me.partner != null);
      setPartnerName(me.partner?.display_name ?? null);
    } catch { /* me refresh handles auth */ }
    try { setProfile(await api.discoveryProfile()); } catch { /* new users */ }
    try { setInvitations(await api.invitations()); } catch { /* ignore */ }
  }, []);

  // 5 s polling while the page is open: drives expiry even without SSE.
  useEffect(() => {
    void refreshStatic();
    let alive = true;
    const poll = async () => {
      try {
        const snap = await api.discovery();
        if (alive) { setSnapshot(snap); setError(null); }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "discovery unavailable");
      }
      try { if (alive) setInvitations(await api.invitations()); } catch { /* ignore */ }
    };
    void poll();
    const timer = setInterval(poll, 5000);
    return () => { alive = false; clearInterval(timer); };
  }, [refreshStatic]);

  const invite = async (userId: string) => {
    try { await api.createInvitation(userId); } catch (e) {
      setError(e instanceof Error ? e.message : "invite failed");
    }
    try { setInvitations(await api.invitations()); } catch { /* ignore */ }
  };

  const respond = async (id: string, accept: boolean) => {
    try {
      await (accept ? api.acceptInvitation(id) : api.declineInvitation(id));
      await refreshStatic();
      refreshMe();
    } catch (e) { setError(e instanceof Error ? e.message : "failed"); }
  };

  const end = async () => {
    try {
      await api.endPartnership();
      await refreshStatic();
      refreshMe();
    } catch (e) { setError(e instanceof Error ? e.message : "failed"); }
  };

  return (
    <main className="page">
      <h1>Discovery</h1>
      {error && <p className="error">{error}</p>}

      {partnered ? (
        <section className="card">
          <h2>Partnership</h2>
          <p>
            Partnered with <strong>{partnerName}</strong>. End the partnership to
            return to nearby discovery.
          </p>
          <button onClick={end}>End partnership</button>
        </section>
      ) : (
        <>
          <ProfileEditor
            profile={profile}
            onProfileChange={setProfile}
            onSaved={() => setEditing(false)}
            editing={editing}
            setEditing={setEditing}
            setError={setError}
          />

          {invitations && invitations.incoming.length > 0 && (
            <section className="card">
              <h2>Invitations</h2>
              {invitations.incoming.map((inv) => (
                <p key={inv.id}>
                  <strong>{inv.from_name}</strong> invited you{" "}
                  <button onClick={() => respond(inv.id, true)}>Accept</button>{" "}
                  <button onClick={() => respond(inv.id, false)}>Decline</button>
                </p>
              ))}
            </section>
          )}

          <section className="card">
            <h2>Nearby</h2>
            {snapshot?.notices.map((n, i) => (
              <p key={i} className="notice">
                {n.message}
                {n.age_seconds != null && n.age_seconds >= 0 ? ` (${n.age_seconds}s ago)` : ""}
              </p>
            ))}
            {snapshot && snapshot.results.length === 0 && <p>No matches nearby.</p>}
            {snapshot?.results.map((r) => (
              <div key={r.user_id} className="discovery-result">
                <strong>{r.display_name}</strong>{" "}
                <span className="muted">
                  shares {r.shared_interests.join(", ")}
                </span>
                <div className="muted">
                  {r.bluetooth && <span>{r.bluetooth.label} · </span>}
                  {r.gps && (
                    <span>
                      ~{r.gps.distance_m} m ({r.gps.freshness === "last_known" ? "last known" : "fresh"})
                      {r.gps.labels.length > 0 && ` — ${r.gps.labels.join("; ")}`}
                      {r.gps.their_age_seconds != null && ` (${r.gps.their_age_seconds}s ago)`}
                    </span>
                  )}
                </div>
                <button onClick={() => invite(r.user_id)}>Invite</button>
              </div>
            ))}
          </section>
        </>
      )}
    </main>
  );
}

function ProfileEditor({
  profile, onProfileChange, onSaved, editing, setEditing, setError,
}: {
  profile: DiscoveryProfile | null;
  onProfileChange: (p: DiscoveryProfile) => void;
  onSaved: () => void;
  editing: boolean;
  setEditing: (v: boolean) => void;
  setError: (e: string | null) => void;
}) {
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [minAge, setMinAge] = useState("18");
  const [maxAge, setMaxAge] = useState("99");
  const [radius, setRadius] = useState("500");
  const [interests, setInterests] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!profile) return;
    setName(profile.display_name ?? "");
    setAge(profile.age?.toString() ?? "");
    setMinAge((profile.pref_min_age ?? 18).toString());
    setMaxAge((profile.pref_max_age ?? 99).toString());
    setRadius(profile.radius_m.toString());
    setInterests(new Set(profile.interests));
  }, [profile]);

  const save = async () => {
    try {
      const p = await api.putDiscoveryProfile({
        display_name: name.trim(),
        age: Number(age), pref_min_age: Number(minAge), pref_max_age: Number(maxAge),
        interests: [...interests].sort(), radius_m: Number(radius),
      });
      setError(null);
      onProfileChange(p);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "save failed");
    }
  };

  const toggleOptIn = async (kind: "bluetooth" | "gps", value: boolean) => {
    try {
      const p = await api.putDiscoverySettings(
        kind === "bluetooth" ? value : (profile?.bluetooth_enabled ?? false),
        kind === "gps" ? value : (profile?.gps_enabled ?? false),
      );
      onProfileChange(p);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed");
    }
  };

  if (!editing) {
    return (
      <section className="card">
        <h2>Profile</h2>
        {profile?.complete ? (
          <p>
            {profile.display_name}, age {profile.age} · wants {profile.pref_min_age}–{profile.pref_max_age} ·
            radius {profile.radius_m} m · likes {profile.interests.join(", ")}
          </p>
        ) : (
          <p className="notice">Profile incomplete — complete it to appear in discovery.</p>
        )}
        <label>
          <input
            type="checkbox"
            checked={profile?.bluetooth_enabled ?? false}
            onChange={(e) => void toggleOptIn("bluetooth", e.target.checked)}
          />{" "}
          Bluetooth discovery
        </label>{" "}
        <label>
          <input
            type="checkbox"
            checked={profile?.gps_enabled ?? false}
            onChange={(e) => void toggleOptIn("gps", e.target.checked)}
          />{" "}
          GPS discovery
        </label>
        <div>
          <button onClick={() => setEditing(true)}>Edit profile</button>
        </div>
      </section>
    );
  }

  return (
    <section className="card">
      <h2>Edit profile</h2>
      <p>
        <label>
          Display name{" "}
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
      </p>
      <p>
        <label>
          Age (18–99){" "}
          <input value={age} onChange={(e) => setAge(e.target.value)} inputMode="numeric" />
        </label>{" "}
        <label>
          Min age{" "}
          <input value={minAge} onChange={(e) => setMinAge(e.target.value)} inputMode="numeric" />
        </label>{" "}
        <label>
          Max age{" "}
          <input value={maxAge} onChange={(e) => setMaxAge(e.target.value)} inputMode="numeric" />
        </label>{" "}
        <label>
          Radius m (100–5000){" "}
          <input value={radius} onChange={(e) => setRadius(e.target.value)} inputMode="numeric" />
        </label>
      </p>
      <p>
        {INTEREST_TAGS.map((tag) => (
          <label key={tag} className="chip">
            <input
              type="checkbox"
              checked={interests.has(tag)}
              onChange={(e) => {
                const next = new Set(interests);
                if (e.target.checked) next.add(tag); else next.delete(tag);
                setInterests(next);
              }}
            />{" "}
            {tag}
          </label>
        ))}
      </p>
      <button onClick={save}>Save</button>{" "}
      <button onClick={() => setEditing(false)}>Cancel</button>
    </section>
  );
}
