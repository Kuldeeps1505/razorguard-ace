import { useEffect, useState } from "react";
import { api, type AuditEvent } from "../../services/api";

export default function AuditPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .audit()
      .then(setEvents)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : String(err)),
      );
  }, []);

  return (
    <>
      <section className="page-head"><div><span className="eyebrow">EVIDENCE LOG</span><h1>Audit Trail</h1><p>Append-only, hash-chained records for every high-risk decision.</p></div><div className="flow-legend"><i /> Tamper-evident</div></section>
      {error && <div className="err">{error}</div>}
      <div className="panel">
        <table className="table">
          <thead>
            <tr>
              <th>When</th>
              <th>Actor</th>
              <th>Action</th>
              <th>Result</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.event_id}>
                <td>{e.created_at}</td>
                <td>{e.actor}</td>
                <td>{e.action}</td>
                <td>{e.result}</td>
                <td>{e.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {events.length === 0 && !error && <div className="empty-state compact"><span>▤</span><h3>No events recorded yet</h3><p>Control-plane decisions will be recorded here automatically.</p></div>}
      </div>
    </>
  );
}
