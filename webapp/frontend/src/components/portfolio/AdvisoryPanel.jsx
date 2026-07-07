import { useState } from "react";
import client from "../../api/client";

// Minimal markdown renderer for the advisory: ### headings, - bullets, **bold**.
function Bold({ text }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((p, i) =>
        p.startsWith("**") && p.endsWith("**")
          ? <strong key={i} style={{ color: "var(--text)" }}>{p.slice(2, -2)}</strong>
          : <span key={i}>{p}</span>
      )}
    </>
  );
}

function AdvisoryBody({ text }) {
  return (
    <div style={{ fontSize: 14, lineHeight: 1.7 }}>
      {text.split("\n").map((line, i) => {
        const t = line.trim();
        if (!t) return <div key={i} style={{ height: 8 }} />;
        if (t.startsWith("### ")) {
          return (
            <h3 key={i} style={{ margin: "14px 0 6px", fontSize: 15, color: "var(--primary)" }}>
              {t.slice(4)}
            </h3>
          );
        }
        if (t.startsWith("- ") || t.startsWith("* ")) {
          return (
            <div key={i} style={{ display: "flex", gap: 8, marginBottom: 4 }}>
              <span style={{ color: "var(--primary)" }}>•</span>
              <span><Bold text={t.slice(2)} /></span>
            </div>
          );
        }
        return <p key={i} style={{ margin: "0 0 6px" }}><Bold text={t} /></p>;
      })}
    </div>
  );
}

export default function AdvisoryPanel() {
  const [advisory, setAdvisory] = useState(null);
  const [isFallback, setIsFallback] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function generate() {
    setLoading(true);
    setError("");
    try {
      const res = await client.get("/api/portfolio/advisory", { timeout: 60000 });
      setAdvisory(res.data.advisory);
      setIsFallback(res.data.is_fallback);
    } catch {
      setError("Could not generate the advisory. Try again in a moment.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2 style={{ margin: 0 }}>🤖 AI Portfolio Advisory</h2>
        <button className="btn btn-primary" onClick={generate} disabled={loading}>
          {loading ? "Analysing…" : advisory ? "Regenerate" : "Generate Advisory"}
        </button>
      </div>
      {!advisory && !loading && !error && (
        <p className="muted" style={{ marginBottom: 0 }}>
          A structured expert read on your finances, allocation and market risks —
          grounded in your live account data.
        </p>
      )}
      {error && <p className="error-text">{error}</p>}
      {isFallback && advisory && (
        <p style={{
          background: "var(--primary-dim)", border: "1px solid var(--card-border)",
          borderRadius: 8, padding: "8px 12px", fontSize: 12, color: "var(--muted)",
        }}>
          AI service unreachable — showing a data-driven summary instead.
        </p>
      )}
      {advisory && <AdvisoryBody text={advisory} />}
    </div>
  );
}
