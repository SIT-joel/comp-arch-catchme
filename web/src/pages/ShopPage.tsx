import { useCallback, useEffect, useState } from "react";
import { api, Me, Reward } from "../api";

export default function ShopPage({ me, refreshMe }: { me: Me; refreshMe: () => Promise<void> }) {
  const [rewards, setRewards] = useState<Reward[]>([]);
  const [points, setPoints] = useState(me.user.points);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const out = await api.rewards();
    setRewards(out.rewards);
    setPoints(out.points);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const buy = async (reward: Reward) => {
    setError(null);
    setSuccess(null);
    setBusyId(reward.id);
    try {
      // Idempotency key is random per click: one key = one purchase attempt.
      const key = `web-${me.user.id}-${reward.id}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const result = await api.purchase(reward.id, key);
      setSuccess(`Purchased ${reward.name} for ${result.price} points. Balance: ${result.balance_after}.`);
      await refresh();
      await refreshMe();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Purchase failed");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <main className="page">
      <section className="card">
        <h2>Badge shop</h2>
        <p className="muted">
          Cosmetic badges only — no monetary value. Points come from completed quests; spending never reduces XP.
          Balance: <strong>{points} points</strong> · Level {me.user.level} · {me.user.lifetime_xp} XP.
        </p>
        {success && <div className="success">{success}</div>}
        {error && <div className="error">{error}</div>}
        <div className="quest-grid">
          {rewards.map((r) => (
            <div key={r.id} className="quest-tile">
              <h3>{r.name}</h3>
              <p className="muted">{r.description}</p>
              <p className="price">{r.price} points</p>
              {r.owned ? (
                <span className="tag owned-tag">owned</span>
              ) : (
                <button disabled={points < r.price || busyId === r.id} onClick={() => buy(r)}>
                  {points < r.price ? "not enough points" : busyId === r.id ? "Buying…" : "Buy badge"}
                </button>
              )}
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
