import { FormEvent, useEffect, useState } from "react";
import { api, type Campaign, type CatalogProduct, type CreateCampaign, type MerchantPolicy } from "../../services/api";

function localDateTime(daysFromNow: number) {
  return new Date(Date.now() + daysFromNow * 86_400_000).toISOString().slice(0, 16);
}

type CampaignForm = Omit<CreateCampaign, "eligible_categories" | "eligible_product_ids" | "valid_from" | "valid_until"> & {
  categories: string;
  valid_from: string;
  valid_until: string;
};

const initialCampaign: CampaignForm = {
  code: "", discount_type: "PERCENTAGE" as const, discount_value: 10, max_discount_minor: 0,
  categories: "", max_uses_per_agent_per_day: 100, max_total_uses: 1000,
  valid_from: localDateTime(0), valid_until: localDateTime(7),
};

export default function MerchantPage() {
  const [merchantId, setMerchantId] = useState(localStorage.getItem("rg_merchant") || "00000000-0000-0000-0000-000000000010");
  const [policy, setPolicy] = useState<MerchantPolicy | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [catalog, setCatalog] = useState<CatalogProduct[]>([]);
  const [campaign, setCampaign] = useState(initialCampaign);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [savingCampaign, setSavingCampaign] = useState(false);

  async function load() {
    setError(""); setMessage(""); localStorage.setItem("rg_merchant", merchantId);
    try {
      const [p, c, cat] = await Promise.all([api.merchantPolicy(merchantId), api.merchantCampaigns(merchantId), api.merchantCatalog(merchantId)]);
      setPolicy(p); setCampaigns(c); setCatalog(cat);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }

  async function toggle(on: boolean) {
    setError("");
    try { setPolicy(on ? await api.enableCommerce(merchantId) : await api.disableCommerce(merchantId)); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }

  async function createCampaign(event: FormEvent) {
    event.preventDefault(); setError(""); setMessage(""); setSavingCampaign(true);
    try {
      const payload: CreateCampaign = {
        code: campaign.code.trim(), discount_type: campaign.discount_type, discount_value: Number(campaign.discount_value),
        max_discount_minor: Number(campaign.max_discount_minor),
        eligible_categories: campaign.categories.split(",").map((value) => value.trim()).filter(Boolean), eligible_product_ids: [],
        max_uses_per_agent_per_day: Number(campaign.max_uses_per_agent_per_day), max_total_uses: Number(campaign.max_total_uses),
        valid_from: new Date(campaign.valid_from).toISOString(), valid_until: new Date(campaign.valid_until).toISOString(),
      };
      const created = await api.createMerchantCampaign(merchantId, payload);
      setCampaigns((existing) => [created, ...existing]);
      setMessage(`Campaign ${created.code} is active and available to eligible agent checkouts.`);
      setCampaign({ ...initialCampaign, valid_from: localDateTime(0), valid_until: localDateTime(7) });
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setSavingCampaign(false); }
  }

  useEffect(() => { void load(); }, []);

  return <>
    <h1>Merchant Control Plane</h1><p className="tag">Kill switch, campaigns, agent-readable catalog.</p>
    <div className="panel"><label>Merchant ID</label><input value={merchantId} onChange={(e) => setMerchantId(e.target.value)} />
      <div className="row"><button className="btn" onClick={() => void load()}>Refresh</button><button className="btn danger" onClick={() => void toggle(false)}>Disable agent commerce</button><button className="btn ghost" onClick={() => void toggle(true)}>Enable</button></div>
      {error && <div className="err">{error}</div>}{message && <div className="ok-msg">{message}</div>}
    </div>
    {policy && <div className="kpis" style={{ marginTop: 16 }}><div className="kpi"><div className="n">{policy.agent_commerce_enabled ? "ON" : "OFF"}</div><div className="l">Kill switch (enabled = agents allowed)</div></div><div className="kpi"><div className="n">₹{(policy.max_autonomous_order_minor / 100).toFixed(0)}</div><div className="l">Max autonomous order</div></div><div className="kpi"><div className="n">{policy.max_discount_pct}%</div><div className="l">Max discount agents may apply</div></div></div>}
    <div className="grid-2" style={{ marginTop: 16 }}>
      <div className="panel"><h3>Campaigns</h3><p className="tag">Create merchant-authorized discounts. Agents cannot invent campaigns.</p>
        <form onSubmit={(event) => void createCampaign(event)}><label>Campaign code</label><input required value={campaign.code} placeholder="WELCOME10" onChange={(e) => setCampaign({ ...campaign, code: e.target.value.toUpperCase() })} />
          <div className="row"><label>Discount type<select value={campaign.discount_type} onChange={(e) => setCampaign({ ...campaign, discount_type: e.target.value as CreateCampaign["discount_type"] })}><option value="PERCENTAGE">Percentage</option><option value="FIXED">Fixed ₹ paise</option></select></label><label>Value<input required min="1" type="number" value={campaign.discount_value} onChange={(e) => setCampaign({ ...campaign, discount_value: Number(e.target.value) })} /></label></div>
          <label>Eligible categories (comma-separated; empty = all)</label><input value={campaign.categories} placeholder="electronics, accessories" onChange={(e) => setCampaign({ ...campaign, categories: e.target.value })} />
          <div className="row"><label>Starts<input required type="datetime-local" value={campaign.valid_from} onChange={(e) => setCampaign({ ...campaign, valid_from: e.target.value })} /></label><label>Ends<input required type="datetime-local" value={campaign.valid_until} onChange={(e) => setCampaign({ ...campaign, valid_until: e.target.value })} /></label></div>
          <div className="row"><label>Usage limit<input required min="1" type="number" value={campaign.max_total_uses} onChange={(e) => setCampaign({ ...campaign, max_total_uses: Number(e.target.value) })} /></label><label>Per-agent daily limit<input required min="1" type="number" value={campaign.max_uses_per_agent_per_day} onChange={(e) => setCampaign({ ...campaign, max_uses_per_agent_per_day: Number(e.target.value) })} /></label></div>
          <div className="row"><label>Discount cap (paise; 0 = no cap)<input required min="0" type="number" value={campaign.max_discount_minor} onChange={(e) => setCampaign({ ...campaign, max_discount_minor: Number(e.target.value) })} /></label><button className="btn" disabled={savingCampaign}>{savingCampaign ? "Creating…" : "Create campaign"}</button></div>
        </form>
        {campaigns.length === 0 ? <p className="tag">No campaigns configured.</p> : <table className="table"><thead><tr><th>Code</th><th>Discount</th><th>Uses</th><th>Valid until</th><th>Status</th></tr></thead><tbody>{campaigns.map((c) => <tr key={c.campaign_id}><td>{c.code}<small>{c.eligible_categories.join(", ") || "All categories"}</small></td><td>{c.discount_type === "PERCENTAGE" ? `${c.discount_value}%` : `₹${(c.discount_value / 100).toFixed(2)}`}</td><td>{c.total_uses}</td><td>{new Date(c.valid_until).toLocaleDateString()}</td><td>{c.status}</td></tr>)}</tbody></table>}
      </div>
      <div className="panel"><h3>Catalog</h3><table className="table"><thead><tr><th>Title</th><th>Category</th><th>Price</th></tr></thead><tbody>{catalog.map((p) => <tr key={p.product_id}><td>{p.title}</td><td>{p.category}</td><td>₹{(p.price_minor / 100).toFixed(2)}</td></tr>)}</tbody></table></div>
    </div>
  </>;
}
