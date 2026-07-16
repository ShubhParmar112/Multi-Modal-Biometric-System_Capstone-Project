import { useState } from "react";

const fmtINR = (v) =>
  "₹" + Number(v || 0).toLocaleString(undefined, { minimumFractionDigits: 2 });

const last4 = (masked) => (masked || "").slice(-4) || "••••";

function Contactless() {
  return (
    <svg className="bank-card-contactless" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      aria-hidden="true">
      <path d="M6.5 8.5a9 9 0 0 1 0 7" />
      <path d="M10 6.5a13 13 0 0 1 0 11" />
      <path d="M13.5 4.5a17 17 0 0 1 0 15" />
    </svg>
  );
}

function BrandCircles() {
  return <div className="bank-card-brand" aria-hidden="true"><span /><span /></div>;
}

function Sparkline({ points }) {
  if (!points || points.length < 2) return null;
  const min = Math.min(...points);
  const range = (Math.max(...points) - min) || 1;
  const coords = points
    .map((v, i) => {
      const x = (i / (points.length - 1)) * 120;
      const y = 20 - ((v - min) / range) * 16;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg className="bank-card-spark" viewBox="0 0 120 22"
      preserveAspectRatio="none" aria-hidden="true">
      <polyline points={coords} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function DebitCard({ card, balance, holder, active }) {
  return (
    <>
      <div className="bank-card-top">
        <div className="bank-card-chip" />
        <span className="bank-card-tag">DEBIT <Contactless /></span>
      </div>
      <div>
        <p className="bank-card-number">
          {active ? (card?.number_masked || "•••• •••• •••• ••••")
                  : `•••• •••• •••• ${last4(card?.number_masked)}`}
        </p>
        <p className="bank-card-balance-label">Available Balance</p>
        <p className="bank-card-balance">{active ? fmtINR(balance) : "₹ ••••••"}</p>
      </div>
      <div className="bank-card-bottom">
        <div>
          <p className="bank-card-label">Card Holder</p>
          <p className="bank-card-holder">{holder}</p>
        </div>
        <BrandCircles />
      </div>
    </>
  );
}

function CreditCard({ card, holder, active }) {
  const limit = card?.credit_limit || 0;
  const outstanding = card?.outstanding || 0;
  const usedPct = limit > 0 ? Math.min((outstanding / limit) * 100, 100) : 0;
  return (
    <>
      <div className="bank-card-top">
        <div className="bank-card-chip" />
        <span className="bank-card-tag">CREDIT <Contactless /></span>
      </div>
      <div>
        <p className="bank-card-number">
          {active ? (card?.number_masked || "•••• •••• •••• ••••")
                  : `•••• •••• •••• ${last4(card?.number_masked)}`}
        </p>
        <p className="bank-card-balance-label">
          Outstanding{active && limit > 0 ? ` · limit ${fmtINR(limit)}` : ""}
        </p>
        <p className="bank-card-balance">{active ? fmtINR(outstanding) : "₹ ••••••"}</p>
        {active && limit > 0 && (
          <div className="bank-card-bar">
            <div className="bank-card-bar-fill" style={{ width: `${usedPct}%` }} />
          </div>
        )}
      </div>
      <div className="bank-card-bottom">
        <div>
          <p className="bank-card-label">Card Holder</p>
          <p className="bank-card-holder">{holder}</p>
        </div>
        <p className="bank-card-subtle">
          {card?.due_date ? `due ${card.due_date}` : `exp ${card?.expiry || "—"}`}
        </p>
      </div>
    </>
  );
}

function InvestCard({ invest, holder, active }) {
  const hasData = invest?.status === "ok";
  const up = hasData && invest.day_change >= 0;
  return (
    <>
      <div className="bank-card-top">
        <svg className="bank-card-contactless" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2" strokeLinecap="round"
          strokeLinejoin="round" aria-hidden="true">
          <path d="M3 17l6-6 4 4 8-8" />
          <path d="M14 7h7v7" />
        </svg>
        <span className="bank-card-tag">INVEST</span>
      </div>
      <div>
        <p className="bank-card-balance-label">Portfolio Value</p>
        {hasData ? (
          <>
            <p className="bank-card-balance">{active ? fmtINR(invest.value) : "₹ ••••••"}</p>
            {active && (
              <>
                <p className="bank-card-delta"
                  style={{ color: up ? "#34D399" : "#FB7185" }}>
                  {up ? "▲" : "▼"} {up ? "+" : "−"}{fmtINR(Math.abs(invest.day_change))}
                  {" "}today ({up ? "+" : ""}{invest.day_change_pct}%)
                </p>
                <Sparkline points={invest.spark} />
              </>
            )}
          </>
        ) : (
          <p className="bank-card-balance" style={{ fontSize: 16 }}>
            No holdings yet
          </p>
        )}
      </div>
      <div className="bank-card-bottom">
        <div>
          <p className="bank-card-label">Card Holder</p>
          <p className="bank-card-holder">{holder}</p>
        </div>
        <p className="bank-card-subtle">
          {hasData
            ? `top: ${invest.top_holding.ticker.replace(".NS", "")} ${invest.top_holding.share_pct}%`
            : "start from Portfolio"}
        </p>
      </div>
    </>
  );
}

// Dashboard hero: debit / credit / invest cards in a focus carousel.
// Credit (the original graphite card) sits front and center by default.
export default function BankCardCarousel({ account, invest, holder }) {
  const debit = account.cards?.find((c) => c.card_type === "debit");
  const credit = account.cards?.find((c) => c.card_type === "credit");
  const slides = [
    { key: "debit", card: debit },
    { key: "credit", card: credit },
    { key: "invest" },
  ];
  const [active, setActive] = useState(1);

  const captions = {
    debit: `${account.account_type.toUpperCase()} · ${account.account_number} · DEBIT exp ${debit?.expiry || "—"}`,
    credit: `CREDIT · ${credit?.number_masked || "—"} · exp ${credit?.expiry || "—"}`,
    invest: invest?.status === "ok"
      ? `INVEST · ${invest.holdings_count} HOLDING${invest.holdings_count === 1 ? "" : "S"} · ${fmtINR(invest.invested)} INVESTED`
      : "INVEST · NO HOLDINGS YET",
  };

  return (
    <div className="bank-card-wrap">
      <div className="card-carousel">
        <button className="carousel-arrow left" aria-label="Previous card"
          disabled={active === 0}
          onClick={() => setActive((a) => Math.max(0, a - 1))}>‹</button>
        {slides.map((s, i) => {
          const d = i - active;
          const pos = d === 0 ? "center"
            : d === -1 ? "left" : d === 1 ? "right"
            : d < 0 ? "far-left" : "far-right";
          const isActive = i === active;
          return (
            <div key={s.key}
              className={`bank-card bank-card--${s.key} pos-${pos}`}
              onClick={() => !isActive && setActive(i)}>
              {s.key === "debit" && (
                <DebitCard card={s.card} balance={account.balance}
                  holder={holder} active={isActive} />
              )}
              {s.key === "credit" && (
                <CreditCard card={s.card} holder={holder} active={isActive} />
              )}
              {s.key === "invest" && (
                <InvestCard invest={invest} holder={holder} active={isActive} />
              )}
            </div>
          );
        })}
        <button className="carousel-arrow right" aria-label="Next card"
          disabled={active === slides.length - 1}
          onClick={() => setActive((a) => Math.min(slides.length - 1, a + 1))}>›</button>
      </div>
      <div className="carousel-dots">
        {slides.map((s, i) => (
          <span key={s.key} className={i === active ? "dot active" : "dot"}
            onClick={() => setActive(i)} />
        ))}
      </div>
      <p className="balance-meta">{captions[slides[active].key]}</p>
    </div>
  );
}
