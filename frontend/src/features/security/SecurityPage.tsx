import { useCallback, useEffect, useState } from "react";
import { api, type SecurityDashboard } from "../../services/api";

const SCENARIOS = ["price_drift", "duplicate_execution", "forged_webhook", "prompt_injection", "merchant_kill_switch", "provider_timeout"];

export default function SecurityPage() {
  const [data, setData] = useState<SecurityDashboard | null>(null);
  const [error, setError] = useState("");
  const [chaosResult, setChaosResult] = useState("");
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [runningScenario, setRunningScenario] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api.security());
      setError("");
      setUpdatedAt(new Date());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void load();
    const interval = window.setInterval(() => void load(), 10_000);
    return () => window.clearInterval(interval);
  }, [load]);

  async function runScenario(scenario: string) {
    setRunningScenario(scenario);
    setError("");
    try {
      const result = await api.chaos(scenario);
      setChaosResult(`${result.status}: ${result.explanation}`);
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunningScenario(null);
    }
  }

  async function seedDemoSignals() {
    setSeeding(true);
    setError("");
    try {
      setData(await api.seedSecurityDemo());
      setUpdatedAt(new Date());
      setChaosResult("Demo telemetry loaded: counters represent safe, non-financial test signals only.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSeeding(false);
    }
  }

  const items: Array<[keyof SecurityDashboard, string]> = [
    ["policy_violations_blocked", "Policy violations blocked"],
    ["duplicate_payments_prevented", "Duplicate payments prevented"],
    ["expired_capabilities_rejected", "Expired capabilities rejected"],
    ["prompt_injections_detected", "Prompt injections detected"],
    ["unknown_payments_reconciled", "Unknown payments reconciled"],
    ["webhook_replays_rejected", "Webhook replays rejected"],
  ];

  return (
    <>
      <section className="page-head">
        <div><span className="eyebrow">TRUST CENTER</span><h1>Security Dashboard</h1><p>Live control-plane outcomes, not probabilistic AI safety scores.</p></div>
        <div className="security-status"><span>{data ? "✓" : "!"}</span><div><b>{data ? "All safeguards active" : "Dashboard unavailable"}</b><small>{updatedAt ? `Live · updated ${updatedAt.toLocaleTimeString()}` : "Waiting for API"}</small></div></div>
      </section>
      {error && <div className="err">{error} <button className="btn ghost" onClick={() => void load()}>Retry</button></div>}
      <div className="kpis">
        {items.map(([key, label]) => <div className="kpi" key={key}><div className="n">{data ? data[key] : "—"}</div><div className="l">{label}</div></div>)}
      </div>
      <div className="panel" style={{ marginTop: 18 }}>
        <span className="eyebrow">SECURITY CHAOS DEMO</span><h3>Prove the control plane fails safely</h3>
        <p className="tag">These are deterministic simulations; they never create payments or mutate production data.</p>
        <div className="row">
          <button className="btn" disabled={seeding || runningScenario !== null} onClick={() => void seedDemoSignals()}>{seeding ? "Loading signals…" : "Load safe demo signals"}</button>
          {SCENARIOS.map((scenario) => <button key={scenario} className="btn ghost" disabled={runningScenario !== null} onClick={() => void runScenario(scenario)}>{runningScenario === scenario ? "Running…" : scenario.replaceAll("_", " ")}</button>)}
        </div>
        {chaosResult && <div className="msg agent" style={{ marginTop: 14 }}>{chaosResult}</div>}
      </div>
    </>
  );
}
