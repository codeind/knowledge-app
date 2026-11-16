"use client";

import Link from "next/link";
import { useState } from "react";
import { api, Card, DOMAIN_NAMES, formatDate } from "@/lib/api";
import DeeperPanel from "./DeeperPanel";

const LABEL_STYLE: Record<string, string> = {
  Fact: "bg-emerald-50 text-emerald-800 border-emerald-200",
  Interpretation: "bg-sky-50 text-sky-800 border-sky-200",
  Opinion: "bg-amber-50 text-amber-800 border-amber-200",
  Disputed: "bg-rose-50 text-rose-800 border-rose-200",
};

export function Badges({ card }: { card: Card }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
      <span className={`rounded-full border px-2 py-0.5 ${LABEL_STYLE[card.label] ?? ""}`}>
        {card.label}
        {card.viewpoint ? ` · ${card.viewpoint}` : ""}
      </span>
      {card.origin === "seed" ? (
        <span className="rounded-full border border-line px-2 py-0.5 text-muted" title="Hand-written sample card; not checked by the verifier">
          Sample
        </span>
      ) : card.verification === "verified" ? (
        <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-emerald-800">Verified</span>
      ) : card.verification === "single_source" ? (
        <span className="rounded-full border border-line px-2 py-0.5 text-muted" title="Claims checked against one source">
          Checked · 1 source
        </span>
      ) : (
        <span className="rounded-full border border-line px-2 py-0.5 text-muted">Unverified</span>
      )}
    </div>
  );
}

export default function CardView({ card, compact = false, showDeeper = true }: { card: Card; compact?: boolean; showDeeper?: boolean }) {
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState(!!card.saved);

  async function toggleSave() {
    const next = !saved;
    setSaved(next);
    try {
      if (next) await api("/api/saves", { method: "POST", body: JSON.stringify({ card_id: card.id }) });
      else await api(`/api/saves/${card.id}`, { method: "DELETE" });
    } catch {
      setSaved(!next);
    }
  }

  return (
    <article className="rounded-2xl border border-line bg-white p-5 shadow-[0_1px_0_rgba(0,0,0,0.03)]">
      <div className="mb-2 flex items-center justify-between gap-2 text-xs text-muted">
        <span>
          {DOMAIN_NAMES[card.domain] ?? card.domain}
          {card.event_date ? ` · ${formatDate(card.event_date)}` : ""}
          {card.section === "learn" ? ` · ${card.card_type}` : ""}
        </span>
        <Badges card={card} />
      </div>
      <h2 className={`card-title font-semibold leading-snug ${compact ? "text-base" : "text-xl"}`}>
        <Link href={`/card/?id=${card.id}`} className="hover:text-accent">
          {card.title}
        </Link>
      </h2>
      <p className={`mt-2 leading-relaxed text-ink/90 ${compact ? "text-sm" : "text-[15px]"}`}>{card.body}</p>

      {!compact && card.sources.length > 0 && (
        <p className="mt-3 text-xs text-muted">
          Source:{" "}
          {card.sources.map((s, i) => (
            <span key={s.id}>
              {i > 0 && " · "}
              <a href={s.url} target="_blank" rel="noreferrer" className="underline decoration-line underline-offset-2 hover:text-accent">
                {s.title}
              </a>{" "}
              <span className="text-muted/80">({s.licence})</span>
            </span>
          ))}
        </p>
      )}

      {!compact && (
        <div className="mt-4 flex items-center gap-2">
          {showDeeper && card.has_depth && (
            <button
              onClick={() => setOpen(!open)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${open ? "bg-ink text-white" : "bg-accent text-white hover:bg-accent/90"}`}
            >
              {open ? "Close" : "Go deeper"}
            </button>
          )}
          <button onClick={toggleSave} className="rounded-full border border-line px-3 py-1.5 text-sm text-muted hover:border-accent hover:text-accent">
            {saved ? "Saved" : "Save"}
          </button>
        </div>
      )}

      {open && <DeeperPanel cardId={card.id} />}
    </article>
  );
}
