import { useEffect, useState } from "react";
import { api, type Consent, type Intent } from "../../services/api";

export default function ConsentPage() {
  const [intentId, setIntentId] = useState(localStorage.getItem("rg_intent") || "");
  const [intent, setIntent] = useState<Intent | null>(null);
  const [availableIntents, setAvailableIntents] = useState<Intent[]>([]);
  const [pending, setPending] = useState<Consent[]>([]);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  async function refresh(requestedIntentId = intentId) {
    setError("");
    try {
      const [consents, intents] = await Promise.all([api.pendingConsents(), api.intents()]);
      setPending(consents);
      setAvailableIntents(intents);

      // Do not depend on a browser-only ID: recover the newest live proposal
      // from the persisted control-plane records after refresh or navigation.
      const selectedId = intents.some((item) => item.intent_id === requestedIntentId)
        ? requestedIntentId
        : intents.find((item) => !["COMPLETED", "FAILED", "EXPIRED", "CANCELLED", "CONSENT_REJECTED"].includes(item.status))?.intent_id || "";

      setIntentId(selectedId);
      if (selectedId) {
        localStorage.setItem("rg_intent", selectedId);
        setIntent(await api.intent(selectedId));
      } else {
        setIntent(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function requestConsent() {
    setError("");
    if (!intentId) {
      setError("Create a purchase proposal in the AI Assistant first.");
      return;
    }
    try {
      const c = await api.requestConsent(intentId);
      localStorage.setItem("rg_intent", intentId);
      setMsg(`Consent ${c.status} · ${c.consent_id}`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function approve(c: Consent) {
    if (!c.consent_token) {
      setError("Missing consent token");
      return;
    }
    try {
      await api.approveConsent(c.consent_id, c.consent_token, c.intent_id);
      setMsg("Approved! Automatically executing pipeline...");
      
      // Automatically run the rest of the pipeline to PAYMENT
      try {
        await api.checkout(c.intent_id);
        setMsg("Approved and successfully executed to payment!");
      } catch (checkoutErr) {
        setError(checkoutErr instanceof Error ? checkoutErr.message : String(checkoutErr));
      }

      await refresh(c.intent_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function reject(c: Consent) {
    try {
      await api.rejectConsent(c.consent_id, "user_rejected");
      setMsg("Rejected");
      await refresh(c.intent_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <>
      <h1>Purchase Authorization</h1>
      <p className="tag">Explicit user consent. No implied approval from chat history.</p>
      <div className="panel">
        <label>Intent ID</label>
        <input value={intentId} onChange={(e) => setIntentId(e.target.value)} />
        {availableIntents.length > 0 && (
          <>
            <label>Saved purchase proposals</label>
            <select value={intentId} onChange={(e) => { setIntentId(e.target.value); void refresh(e.target.value); }}>
              {availableIntents.map((item) => (
                <option key={item.intent_id} value={item.intent_id}>
                  {item.category} · ₹{(item.final_amount_minor / 100).toFixed(2)} · {item.status}
                </option>
              ))}
            </select>
          </>
        )}
        <div className="row">
          <button className="btn ghost" onClick={() => void refresh()}>
            Load
          </button>
          <button className="btn" onClick={() => void requestConsent()}>
            Request consent
          </button>
        </div>
        {intent && (
          <div className="msg agent" style={{ marginTop: 16 }}>
            Product: {intent.product_id}
            {"\n"}Merchant: {intent.merchant_id}
            {"\n"}Amount: ₹{(intent.amount_minor / 100).toFixed(2)} {intent.currency}
            {"\n"}Category: {intent.category}
            {"\n"}Status: {intent.status}
          </div>
        )}
        <h3>Pending consents</h3>
        {pending.length === 0 && <div className="tag">None pending.</div>}
        {pending.map((c) => (
          <div key={c.consent_id} className="panel" style={{ marginTop: 8 }}>
            <div>
              {c.consent_id} · intent {c.intent_id}
            </div>
            <div className="row">
              <button className="btn" onClick={() => void approve(c)}>
                Approve
              </button>
              <button className="btn danger" onClick={() => void reject(c)}>
                Reject
              </button>
            </div>
          </div>
        ))}
        {msg && <div className="ok-msg">{msg}</div>}
        {error && <div className="err">{error}</div>}
      </div>
    </>
  );
}
