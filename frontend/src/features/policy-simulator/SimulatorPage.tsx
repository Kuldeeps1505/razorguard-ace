import { useState } from "react";
import { api, type PolicyDecision } from "../../services/api";

export default function SimulatorPage() {
  const [merchantId, setMerchantId] = useState(
    localStorage.getItem("rg_merchant") || "00000000-0000-0000-0000-000000000010",
  );
  const [productId, setProductId] = useState(
    "00000000-0000-0000-0000-000000000011",
  );
  const [amount, setAmount] = useState("249900");
  const [category, setCategory] = useState("electronics");
  const [maxTxn, setMaxTxn] = useState("300000");
  const [decision, setDecision] = useState<PolicyDecision | null>(null);
  const [error, setError] = useState("");

  async function run() {
    setError("");
    try {
      const res = await api.simulate({
        amount_minor: Number(amount),
        currency: "INR",
        category,
        merchant_id: merchantId,
        product_id: productId,
        payment_method: "UPI",
        quantity: 1,
        override_max_single_transaction_minor: Number(maxTxn),
      });
      setDecision(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  const tone =
    decision?.decision === "DENY"
      ? "deny"
      : decision?.decision === "ASK_USER"
        ? "ask"
        : "ok";

  return (
    <>
      <h1>Policy Simulator</h1>
      <p className="tag">No side effects. Dual-sided user + merchant rules.</p>
      <div className="grid-2">
        <div className="panel">
          <label>Amount (paise)</label>
          <input value={amount} onChange={(e) => setAmount(e.target.value)} />
          <label>Category</label>
          <input value={category} onChange={(e) => setCategory(e.target.value)} />
          <label>Merchant ID</label>
          <input value={merchantId} onChange={(e) => setMerchantId(e.target.value)} />
          <label>Product ID</label>
          <input value={productId} onChange={(e) => setProductId(e.target.value)} />
          <label>User max single txn (paise)</label>
          <input value={maxTxn} onChange={(e) => setMaxTxn(e.target.value)} />
          <div className="row">
            <button className="btn" onClick={() => void run()}>
              Simulate
            </button>
          </div>
          {error && <div className="err">{error}</div>}
        </div>
        <div className="panel">
          {decision ? (
            <>
              <span className={`pill ${tone}`}>{decision.decision}</span>
              <p>{decision.reason}</p>
              <table className="table">
                <thead>
                  <tr>
                    <th>Rule</th>
                    <th>Pass</th>
                    <th>Why</th>
                  </tr>
                </thead>
                <tbody>
                  {decision.rule_results.map((r) => (
                    <tr key={r.rule_name}>
                      <td>{r.rule_name}</td>
                      <td>{r.passed ? "yes" : "no"}</td>
                      <td>{r.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : (
            <div className="tag">Run a hypothetical purchase.</div>
          )}
        </div>
      </div>
    </>
  );
}
