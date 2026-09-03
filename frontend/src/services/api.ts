export type AgentChatResponse = {
  status: string;
  message?: string | null;
  intent?: Record<string, unknown> | null;
  upsells?: Array<{
    product_id: string;
    title: string;
    category: string;
    price_minor: number;
    currency: string;
    reason: string;
  }>;
};

export type PolicyDecision = {
  decision: "APPROVE" | "DENY" | "ASK_USER";
  reason: string;
  blocking_rule: string | null;
  rule_results: Array<{
    rule_name: string;
    passed: boolean;
    reason: string;
    rule_value: string;
    actual_value: string;
  }>;
};

export type Intent = {
  intent_id: string;
  status: string;
  amount_minor: number;
  final_amount_minor: number;
  currency: string;
  category: string;
  merchant_id: string;
  product_id: string;
  protocol_source: string;
  expires_at: string;
};

export type Consent = {
  consent_id: string;
  intent_id: string;
  status: string;
  mode: string;
  expires_at: string;
  consent_token?: string | null;
};

export type AuditEvent = {
  event_id: string;
  action: string;
  result: string;
  actor: string;
  reason?: string | null;
  created_at: string;
};

export type SecurityDashboard = {
  policy_violations_blocked: number;
  duplicate_payments_prevented: number;
  expired_capabilities_rejected: number;
  prompt_injections_detected: number;
  unknown_payments_reconciled: number;
  webhook_replays_rejected: number;
  payments_unknown: number;
  consent_requested: number;
  consent_granted: number;
  consent_rejected: number;
};

export type MerchantPolicy = {
  policy_id: string;
  merchant_id: string;
  version: number;
  agent_commerce_enabled: boolean;
  max_autonomous_order_minor: number;
  max_discount_pct: number;
  max_agent_txns_per_day: number;
  refund_requires_human: boolean;
};

export type Campaign = {
  campaign_id: string;
  code: string;
  discount_type: string;
  discount_value: number;
  max_discount_minor: number;
  eligible_categories: string[];
  status: string;
  total_uses: number;
  valid_from: string;
  valid_until: string;
};

export type CreateCampaign = {
  code: string;
  discount_type: "PERCENTAGE" | "FIXED";
  discount_value: number;
  max_discount_minor: number;
  eligible_categories: string[];
  eligible_product_ids: string[];
  max_uses_per_agent_per_day: number;
  max_total_uses: number;
  valid_from: string;
  valid_until: string;
};

export type CatalogProduct = {
  product_id: string;
  title: string;
  category: string;
  price_minor: number;
  currency: string;
  availability: string;
};

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      const isHtml = /<\/?html/i.test(text);
      throw new Error(
        isHtml
          ? "The API is temporarily unavailable (the proxy returned an HTML error page). Check the api container logs and try again."
          : "The API returned an invalid response. Check the api container logs.",
      );
    }
  }
  if (!res.ok) {
    const errorData = data as { error?: { message?: unknown }; detail?: unknown } | null;
    const msg = errorData?.error?.message || errorData?.detail || res.statusText;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data as T;
}

export const api = {
  chat: (message: string, merchantId: string, sessionId: string) =>
    request<AgentChatResponse>("/agent/chat", {
      method: "POST",
      body: JSON.stringify({
        message,
        merchant_id: merchantId,
        session_id: sessionId,
      }),
    }),
  simulate: (body: Record<string, unknown>) =>
    request<PolicyDecision>("/policy/simulate", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  intents: () => request<Intent[]>("/intents"),
  deleteIntent: (id: string) => request(`intents/${id}`, { method: "DELETE" }),
  deleteAllIntents: () => request(`intents`, { method: "DELETE" }),
  intent: (id: string) => request<Intent>(`/intents/${id}`),
  requestConsent: (intentId: string) =>
    request<Consent>(`/intents/${intentId}/consent`, { method: "POST" }),
  pendingConsents: () => request<Consent[]>("/consents/pending"),
  approveConsent: (consentId: string, token: string, intentId: string) =>
    request<Consent>(`/consents/${consentId}/approve`, {
      method: "POST",
      body: JSON.stringify({ consent_token: token, intent_id: intentId }),
    }),
  rejectConsent: (consentId: string, reason: string) =>
    request<Consent>(`/consents/${consentId}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  audit: () => request<AuditEvent[]>("/audit/events"),
  security: () => request<SecurityDashboard>("/security/dashboard"),
  seedSecurityDemo: () => request<SecurityDashboard>("/security/demo-seed", { method: "POST" }),
  chaos: (scenario: string) => request<{ scenario: string; status: string; explanation: string; side_effects: boolean }>("/chaos/simulate", {
    method: "POST", body: JSON.stringify({ scenario }),
  }),
  merchantPolicy: (id: string) => request<MerchantPolicy>(`/merchants/${id}/policy`),
  merchantCampaigns: (id: string) => request<Campaign[]>(`/merchants/${id}/campaigns`),
  createMerchantCampaign: (id: string, campaign: CreateCampaign) =>
    request<Campaign>(`/merchants/${id}/campaigns`, {
      method: "POST",
      body: JSON.stringify(campaign),
    }),
  merchantCatalog: (id: string) => request<CatalogProduct[]>(`/merchants/${id}/catalog`),
  disableCommerce: (id: string) =>
    request<MerchantPolicy>(`/merchants/${id}/disable-agent-commerce`, {
      method: "POST",
    }),
  enableCommerce: (id: string) =>
    request<MerchantPolicy>(`/merchants/${id}/enable-agent-commerce`, {
      method: "POST",
    }),
  checkout: (intentId: string) =>
    request<unknown>("/payments/checkout", {
      method: "POST",
      body: JSON.stringify({ intent_id: intentId }),
    }),
};
