import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAdvisor } from "../context/AdvisorContext";

// Compact presentation of the same AI Advisor conversation, docked
// bottom-right. The maximize control navigates to the full /advisor tab;
// state lives in AdvisorContext so the chat continues seamlessly there.
export default function MiniAdvisor() {
  const { messages, loading, send } = useAdvisor();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const navigate = useNavigate();
  const bottomRef = useRef(null);

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, open]);

  function submit() {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    send(text);
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        title="AI Advisor"
        style={{
          position: "fixed", bottom: 24, right: 24, zIndex: 60,
          width: 56, height: 56, borderRadius: "50%", border: "none",
          background: "var(--primary)", color: "#0D1B2A",
          fontSize: 26, cursor: "pointer", boxShadow: "var(--shadow-md)",
        }}
      >
        🤖
      </button>
    );
  }

  return (
    <div style={{
      position: "fixed", bottom: 24, right: 24, zIndex: 60,
      width: 340, height: 440, display: "flex", flexDirection: "column",
      background: "var(--card-solid)", border: "1px solid var(--card-border-strong)",
      borderRadius: 14, boxShadow: "var(--shadow-md)", overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 14px", borderBottom: "1px solid var(--card-border)",
      }}>
        <strong style={{ fontSize: 14 }}>🤖 AI Advisor</strong>
        <div style={{ display: "flex", gap: 6 }}>
          <button
            title="Open the full AI Advisor tab"
            onClick={() => navigate("/advisor")}
            style={{
              background: "transparent", border: "1px solid var(--card-border)",
              borderRadius: 6, color: "var(--text)", cursor: "pointer",
              padding: "2px 8px", fontSize: 13,
            }}
          >⛶</button>
          <button
            title="Minimize"
            onClick={() => setOpen(false)}
            style={{
              background: "transparent", border: "1px solid var(--card-border)",
              borderRadius: 6, color: "var(--text)", cursor: "pointer",
              padding: "2px 8px", fontSize: 13,
            }}
          >—</button>
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: 12 }}>
        {messages.map((m, i) => (
          <div key={i} style={{
            display: "flex",
            justifyContent: m.role === "assistant" ? "flex-start" : "flex-end",
            marginBottom: 8,
          }}>
            <div style={{
              maxWidth: "85%", padding: "7px 10px", fontSize: 13, lineHeight: 1.5,
              whiteSpace: "pre-wrap",
              borderRadius: m.role === "assistant"
                ? "4px 10px 10px 10px" : "10px 4px 10px 10px",
              background: m.role === "assistant" ? "var(--card)" : "var(--primary)",
              color: m.role === "assistant" ? "var(--text)" : "#0D1B2A",
              border: m.role === "assistant"
                ? "1px solid var(--card-border)" : "none",
            }}>
              {m.text}
            </div>
          </div>
        ))}
        {loading && (
          <p className="muted" style={{ fontSize: 12 }}>Advisor is typing…</p>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{
        display: "flex", gap: 6, padding: 10,
        borderTop: "1px solid var(--card-border)",
      }}>
        <input
          className="input"
          style={{ margin: 0, flex: 1, fontSize: 13 }}
          placeholder="Ask about your finances…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
          }}
          disabled={loading}
        />
        <button className="btn btn-primary"
          style={{ margin: 0, padding: "6px 12px" }}
          onClick={submit} disabled={loading || !input.trim()}>
          ➤
        </button>
      </div>
    </div>
  );
}
