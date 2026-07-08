import { useEffect, useRef, useState } from "react";
import { useAdvisor } from "../context/AdvisorContext";

const SUGGESTIONS = [
  "What is my current balance?",
  "How much did I spend this month?",
  "What are my biggest expense categories?",
  "How much did I save this month?",
  "How much did I spend on food this month?",
  "Show my spending over the last 3 months",
  "Where should I invest my money?",
  "What is my investment risk profile?",
  "Give me a monthly financial summary",
  "Show my recent transactions",
];

// Render **bold** markdown inline without a library
function FormattedText({ text }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((p, i) =>
        p.startsWith("**") && p.endsWith("**")
          ? <strong key={i}>{p.slice(2, -2)}</strong>
          : <span key={i}>{p}</span>
      )}
    </>
  );
}

function Message({ role, text }) {
  const isBot = role === "assistant";
  return (
    <div style={{
      display: "flex",
      justifyContent: isBot ? "flex-start" : "flex-end",
      marginBottom: 12,
      alignItems: "flex-end",
      gap: 8,
    }}>
      {isBot && (
        <div style={{
          width: 30, height: 30, borderRadius: "50%",
          background: "var(--primary)", color: "#0D1B2A",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 14, fontWeight: 700, flexShrink: 0,
        }}>A</div>
      )}
      <div style={{
        maxWidth: "72%",
        padding: "10px 14px",
        borderRadius: isBot ? "4px 14px 14px 14px" : "14px 4px 14px 14px",
        background: isBot ? "var(--card)" : "var(--primary)",
        color: isBot ? "var(--text)" : "#0D1B2A",
        border: isBot ? "1px solid var(--card-border)" : "none",
        fontSize: 14,
        lineHeight: 1.65,
        whiteSpace: "pre-wrap",
      }}>
        <FormattedText text={text} />
      </div>
      {!isBot && (
        <div style={{
          width: 30, height: 30, borderRadius: "50%",
          background: "var(--card-border)", color: "var(--text)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 14, fontWeight: 700, flexShrink: 0,
        }}>U</div>
      )}
    </div>
  );
}

function TypingIndicator() {
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "flex-end", marginBottom: 12 }}>
      <div style={{
        width: 30, height: 30, borderRadius: "50%",
        background: "var(--primary)", color: "#0D1B2A",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 14, fontWeight: 700, flexShrink: 0,
      }}>A</div>
      <div style={{
        padding: "12px 16px",
        background: "var(--card)",
        border: "1px solid var(--card-border)",
        borderRadius: "4px 14px 14px 14px",
        display: "flex", gap: 5, alignItems: "center",
      }}>
        {[0, 1, 2].map(i => (
          <div key={i} style={{
            width: 7, height: 7, borderRadius: "50%",
            background: "var(--muted)",
            animation: "bounce 1.2s infinite",
            animationDelay: `${i * 0.2}s`,
          }} />
        ))}
      </div>
    </div>
  );
}

export default function Advisor() {
  // The conversation lives in AdvisorContext so it is shared with the
  // mini widget on the Portfolio page — maximize/minimize keeps context.
  const { messages, loading, send: sendShared, clearChat } = useAdvisor();
  const [input, setInput] = useState("");
  const bottomRef = useRef(null);
  const inputRef  = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send(text) {
    const message = (text ?? input).trim();
    if (!message || loading) return;
    setInput("");
    await sendShared(message);
    inputRef.current?.focus();
  }

  function handleKey(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="page" style={{ maxWidth: 800 }}>
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 4 }}>
        <div>
          <h1 style={{ margin: 0 }}>AI Financial Advisor</h1>
          <p className="muted" style={{ margin: "4px 0 0" }}>
            Powered by Llama 3.3 70B via Groq · Answers use your real account data
          </p>
        </div>
        <button className="btn btn-secondary" style={{ marginTop: 6 }} onClick={clearChat}>
          Clear chat
        </button>
      </div>

      {/* ── Suggestion chips ────────────────────────────────────────────── */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, margin: "16px 0" }}>
        {SUGGESTIONS.map(s => (
          <button
            key={s}
            onClick={() => send(s)}
            disabled={loading}
            style={{
              cursor: "pointer",
              background: "transparent",
              border: "1px solid var(--card-border)",
              borderRadius: 14,
              padding: "4px 12px",
              fontSize: 12,
              color: "var(--primary)",
              whiteSpace: "nowrap",
            }}
          >
            {s}
          </button>
        ))}
      </div>

      {/* ── Chat window ─────────────────────────────────────────────────── */}
      <div style={{
        background: "var(--card)",
        border: "1px solid var(--card-border)",
        borderRadius: 10,
        padding: "16px 16px 8px",
        minHeight: 380,
        maxHeight: 520,
        overflowY: "auto",
        marginBottom: 12,
      }}>
        {messages.map((m, i) => (
          <Message key={i} role={m.role} text={m.text} />
        ))}
        {loading && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* ── Input row ───────────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 10 }}>
        <input
          ref={inputRef}
          className="input"
          style={{ marginBottom: 0, flex: 1 }}
          placeholder="Ask anything about your finances…"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          disabled={loading}
        />
        <button
          className="btn btn-primary"
          style={{ marginTop: 0 }}
          onClick={() => send()}
          disabled={loading || !input.trim()}
        >
          Send
        </button>
      </div>

      {/* Bouncing dot animation */}
      <style>{`
        @keyframes bounce {
          0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
          30% { transform: translateY(-6px); opacity: 1; }
        }
      `}</style>
    </div>
  );
}
