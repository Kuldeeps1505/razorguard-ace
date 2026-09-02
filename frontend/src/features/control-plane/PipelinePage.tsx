import { useEffect, useRef, useState } from "react";
import { api, type Intent } from "../../services/api";

const STAGES = [
  "CREATED",
  "POLICY",
  "CONSENT",
  "CAPABILITY",
  "EXECUTION",
  "PAYMENT",
] as const;

function activeIndex(status: string): number {
  const map: Record<string, number> = {
    CREATED: 0,
    VALIDATING: 0,
    POLICY_PENDING: 1,
    POLICY_APPROVED: 1,
    POLICY_BLOCKED: 1,
    AWAITING_CONSENT: 2,
    CONSENT_GRANTED: 2,
    CONSENT_REJECTED: 2,
    AUTHORIZED: 3,
    EXECUTING: 4,
    VERIFYING: 4,
    UNKNOWN: 4,
    // Razorpay order creation completed successfully. Payment capture is
    // finalized later by the provider webhook, but the full checkout pipeline
    // has reached its final UI stage.
    SUBMITTED: 5,
    COMPLETED: 5,
    FAILED: 5,
  };
  return map[status] ?? 0;
}

export default function PipelinePage() {
  const [intents, setIntents] = useState<Intent[]>([]);
  const [error, setError] = useState("");
  // Track visual simulation state: { [intentId]: { stageIndex, status } }
  const [simulations, setSimulations] = useState<Record<string, { stageIndex: number; status: string }>>({});

  // Use a ref to track which intents are CURRENTLY being simulated
  // This avoids stale closure issues with the polling interval
  const runningRef = useRef<Set<string>>(new Set());

  async function fetchIntents() {
    try {
      const data = await api.intents();
      setIntents(data);

      // Auto-trigger pipeline for any CREATED intent not already running
      // Enforce only one active pipeline at a time
      if (runningRef.current.size === 0) {
        for (const intent of data) {
          if (intent.status === "CREATED" && !runningRef.current.has(intent.intent_id)) {
            void simulatePipeline(intent.intent_id);
            break; // only start one at a time
          }
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    void fetchIntents();
    // Poll every 4 seconds to keep the control plane dynamic without hammering the API
    const interval = setInterval(() => void fetchIntents(), 4000);
    return () => clearInterval(interval);
  }, []);

  async function simulatePipeline(intentId: string) {
    // Guard: mark as running immediately to prevent re-entry from polling
    if (runningRef.current.has(intentId)) return;
    runningRef.current.add(intentId);

    const setSimState = (idx: number, status: string) => {
      setSimulations((prev) => ({ ...prev, [intentId]: { stageIndex: idx, status } }));
    };

    const delay = (ms: number) => new Promise((res) => setTimeout(res, ms));

    // Start visual animation immediately
    setSimState(0, "CREATED");

    // Fire the backend checkout call ONCE in the background
    const checkoutPromise = api.checkout(intentId).catch((err) => {
      console.error("Checkout error:", err);
    });

    // Animate through stages while backend processes
    await delay(600);
    setSimState(1, "POLICY_PENDING");
    await delay(700);
    setSimState(1, "POLICY_APPROVED");
    await delay(700);
    setSimState(2, "AWAITING_CONSENT");
    await delay(700);
    setSimState(2, "CONSENT_GRANTED");
    await delay(700);
    setSimState(3, "AUTHORIZED");
    await delay(700);
    setSimState(4, "EXECUTING");

    // Wait for backend to actually finish
    await checkoutPromise;
    await delay(500);

    // Clear simulation state and sync with real backend data
    runningRef.current.delete(intentId);
    setSimulations((prev) => {
      const next = { ...prev };
      delete next[intentId];
      return next;
    });

    // Refetch to get real final status
    try {
      const updated = await api.intents();
      setIntents(updated);
    } catch {
      // ignore
    }
  }

  return (
    <>
      <section className="page-head">
        <div>
          <span className="eyebrow">LIVE OPERATIONS</span>
          <h1>Control Plane</h1>
          <p>Every agent-led purchase is evaluated through a deterministic, inspectable lifecycle.</p>
        </div>
        <div className="flow-legend"><i /> Secure processing</div>
      </section>
      {error && <div className="err">{error}</div>}
      {intents.length === 0 && !error && (
        <div className="panel empty-state">
          <span>◎</span>
          <h3>No purchase intents yet</h3>
          <p>Use the buyer assistant to propose a purchase. Its lifecycle will appear here.</p>
        </div>
      )}
      {intents.map((intent) => {
        const sim = simulations[intent.intent_id];
        const isRunning = runningRef.current.has(intent.intent_id);
        const displayStatus = sim ? sim.status : intent.status;
        const idx = sim ? sim.stageIndex : activeIndex(displayStatus);
        const failed =
          displayStatus.includes("BLOCKED") ||
          displayStatus.includes("REJECTED") ||
          displayStatus === "FAILED";

        return (
          <div key={intent.intent_id} className="panel" style={{ marginBottom: 16 }}>
            <div className="intent-summary">
              <div>
                <span className="eyebrow">{intent.protocol_source}</span>
                <b>{intent.category} purchase</b>
                <small>{intent.intent_id}</small>
              </div>
              <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
                {isRunning && (
                  <span className="eyebrow" style={{ color: "var(--accent)", letterSpacing: "0.05em" }}>
                    ⟳ Processing…
                  </span>
                )}
                <strong>₹{(intent.amount_minor / 100).toFixed(2)}</strong>
                <span className={`pill ${failed ? "deny" : "ok"}`}>{displayStatus}</span>
                {/* Delete / Stop button */}
                <button
                  onClick={async (e) => {
                    e.stopPropagation();
                    try {
                      await api.deleteIntent(intent.intent_id);
                      await fetchIntents();
                    } catch (err) {
                      console.error(err);
                    }
                  }}
                  style={{ marginLeft: '8px', background: 'transparent', border: 'none', color: 'var(--danger)', cursor: 'pointer' }}
                  title="Cancel this intent"
                >✖</button>
              </div>
            </div>
            <div className="pipeline" style={{ marginTop: 12 }}>
              {STAGES.map((stage, i) => (
                <div
                  key={stage}
                  className={`stage ${i <= idx ? "on" : ""} ${failed && i === idx ? "fail" : ""}`}
                >
                  <div className="tag">{i + 1}</div>
                  <strong>{stage}</strong>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </>
  );
}
