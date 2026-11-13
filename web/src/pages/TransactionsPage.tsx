import { useEffect, useState } from "react";
import { api, Transaction } from "../api";

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);

  useEffect(() => {
    void api.transactions().then((out) => setTransactions(out.transactions));
  }, []);

  return (
    <main className="page">
      <section className="card">
        <h2>Point &amp; XP history</h2>
        {transactions.length === 0 ? (
          <div className="muted">No transactions yet — complete a quest to earn your first award.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Kind</th>
                <th>Points</th>
                <th>XP</th>
                <th>Balance after</th>
                <th>Reference</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((t) => (
                <tr key={t.id}>
                  <td>{new Date(t.created_at).toLocaleString()}</td>
                  <td>{t.kind.replace("_", " ")}</td>
                  <td className={t.delta > 0 ? "pos" : "neg"}>
                    {t.delta > 0 ? "+" : ""}
                    {t.delta}
                  </td>
                  <td className={t.xp_delta > 0 ? "pos" : ""}>{t.xp_delta > 0 ? `+${t.xp_delta}` : "—"}</td>
                  <td>{t.balance_after}</td>
                  <td className="muted">{t.reward_id ?? (t.session_id ? `session ${t.session_id.slice(0, 8)}…` : "")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
