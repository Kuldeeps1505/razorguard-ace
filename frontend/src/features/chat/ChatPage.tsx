import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../services/api";

const DEFAULT_MERCHANT = "00000000-0000-0000-0000-000000000010";
const CHAT_SESSION_KEY = "rg_chat_session";
const CHAT_LOG_KEY = "rg_chat_log";

type ChatMessage = {
  role: string;
  text: string;
  intentId?: string;
  upsells?: Array<{ title: string; category: string; price_minor: number; currency: string; reason: string }>;
};

function getOrCreateSessionId(): string {
  const existing = localStorage.getItem(CHAT_SESSION_KEY);
  if (existing) return existing;

  const sessionId = `sess-${crypto.randomUUID()}`;
  localStorage.setItem(CHAT_SESSION_KEY, sessionId);
  return sessionId;
}

function createSessionId(): string {
  const sessionId = `sess-${crypto.randomUUID()}`;
  localStorage.setItem(CHAT_SESSION_KEY, sessionId);
  return sessionId;
}

function loadChatLog(): ChatMessage[] {
  try {
    const saved = localStorage.getItem(CHAT_LOG_KEY);
    const parsed: unknown = saved ? JSON.parse(saved) : [];
    return Array.isArray(parsed) ? parsed as ChatMessage[] : [];
  } catch {
    return [];
  }
}

export default function ChatPage() {
  const navigate = useNavigate();
  const [merchantId, setMerchantId] = useState(
    () => localStorage.getItem("rg_merchant") || DEFAULT_MERCHANT,
  );
  const [sessionId, setSessionId] = useState(getOrCreateSessionId);
  const [draft, setDraft] = useState(
    "Find me headphones under ₹3,000 and buy the best one.",
  );
  const [log, setLog] = useState<ChatMessage[]>(loadChatLog);
  const [error, setError] = useState("");

  function clearChat() {
    localStorage.removeItem(CHAT_LOG_KEY);
    localStorage.removeItem("rg_intent");
    setLog([]);
    setSessionId(createSessionId());
    setError("");
  }

  async function send() {
    const message = draft.trim();
    if (!message) return;
    setError("");
    setDraft("");
    localStorage.setItem("rg_merchant", merchantId);
    const addMessage = (entry: ChatMessage) => {
      setLog((current) => {
        const next = [...current, entry];
        localStorage.setItem(CHAT_LOG_KEY, JSON.stringify(next));
        return next;
      });
    };
    addMessage({ role: "user", text: message });
    try {
      const res = await api.chat(message, merchantId, sessionId);
      const text =
        res.message ||
        (res.intent
          ? "Purchase proposal saved. Review the canonical checkout and explicitly authorize it before payment can continue."
          : JSON.stringify(res));
      const intentId = res.intent?.intent_id;
      addMessage({
        role: "agent",
        text,
        intentId: typeof intentId === "string" ? intentId : undefined,
        upsells: res.upsells,
      });
      if (typeof intentId === "string") {
        localStorage.setItem("rg_intent", intentId);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <>
      <section className="page-head hero-head">
        <div><span className="eyebrow">AGENTIC COMMERCE</span><h1>Shop with confidence.</h1><p>Ask the buyer agent to discover the right product. RazorGuard keeps every payment bounded, explainable and gated.</p></div>
        <div className="trust-mark"><span>✓</span><div><b>Protected checkout</b><small>AI proposes. You approve.</small></div></div>
      </section>
      <div className="assistant-layout">
        <section className="panel chat-panel">
          <div className="panel-title"><div><h2>Buyer assistant</h2><p>Find, compare and propose purchases.</p></div><div className="chat-actions"><button className="btn ghost clear-chat" onClick={clearChat} disabled={log.length === 0}>Clear chat</button><span className="live-pill"><i /> Online</span></div></div>
          <div className="chat-feed">
            {log.length === 0 && <div className="welcome-chat"><span>✦</span><h3>What would you like to buy?</h3><p>Try: “Find wireless headphones under ₹3,000.”</p></div>}
            {log.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                <strong>{m.role === "user" ? "You" : "RazorGuard agent"}</strong>{"\n"}{m.text}
                {m.intentId && <div className="proposal-action"><span>Intent {m.intentId}</span><button className="btn" onClick={() => { localStorage.setItem("rg_intent", m.intentId!); navigate("/consent"); }}>Review &amp; authorize</button></div>}
                {m.upsells && m.upsells.length > 0 && <div className="upsell-list"><strong>Complete your order</strong>{m.upsells.map((item) => <div className="upsell-card" key={item.title}><div><b>{item.title}</b><small>{item.category} · ₹{(item.price_minor / 100).toFixed(2)}</small></div><button className="btn ghost" onClick={() => setDraft(`Add ${item.title} to my order`)}>Add with agent</button></div>)}</div>}
              </div>
            ))}
          </div>
          <div className="composer"><textarea aria-label="Message" value={draft} onChange={(e) => setDraft(e.target.value)} /><div><span>Enter to send</span><button className="btn" onClick={() => void send()}>Send <b>→</b></button></div></div>
          {error && <div className="err">{error}</div>}
        </section>
        <aside className="assistant-side"><div className="panel"><span className="eyebrow">ACTIVE MERCHANT</span><label>Merchant ID</label><input value={merchantId} onChange={(e) => setMerchantId(e.target.value)} /><div className="side-note"><span>◈</span><p><b>Safe by default</b>Your agent cannot execute a payment or override policy.</p></div></div><div className="panel how-card"><h3>How it works</h3><ol><li>Tell the agent what you need</li><li>Review its purchase proposal</li><li>Approve only when required</li></ol></div></aside>
      </div>
    </>
  );
}
