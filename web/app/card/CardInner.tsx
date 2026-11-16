"use client";

import { useSearchParams } from "next/navigation";
import { Badges } from "@/components/CardView";
import DeeperPanel from "@/components/DeeperPanel";
import { Status, useApi } from "@/components/useApi";
import { Card, DOMAIN_NAMES, formatDate } from "@/lib/api";

const VERDICT: Record<string, string> = {
  supported: "text-emerald-700",
  partial: "text-amber-700",
  unsupported: "text-rose-700",
  unchecked: "text-muted",
};

export default function CardInner() {
  const id = useSearchParams().get("id") ?? "";
  const { data: card, error } = useApi<Card>(id ? `/api/cards/${id}` : null);

  return (
    <div>
      <Status error={error} loading={!card && !error} />
      {card && (
        <article className="rounded-2xl border border-line bg-white p-6">
          <div className="mb-2 flex items-center justify-between gap-2 text-xs text-muted">
            <span>
              {card.section === "news" ? "News" : "Learn"} · {DOMAIN_NAMES[card.domain] ?? card.domain}
              {card.event_date ? ` · ${formatDate(card.event_date)}` : ""}
            </span>
            <Badges card={card} />
          </div>
          <h1 className="card-title text-2xl font-semibold leading-snug">{card.title}</h1>
          <p className="mt-3 text-[16px] leading-relaxed">{card.body}</p>

          <section className="mt-6">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted">Sources</h3>
            <ul className="mt-2 space-y-1 text-sm">
              {card.sources.map((s) => (
                <li key={s.id}>
                  <a href={s.url} target="_blank" rel="noreferrer" className="underline decoration-line underline-offset-2 hover:text-accent">
                    {s.title}
                  </a>{" "}
                  <span className="text-xs text-muted">· {s.licence}</span>
                </li>
              ))}
            </ul>
          </section>

          {card.claims && card.claims.length > 0 && (
            <section className="mt-6">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-muted">
                Claims checked{card.quality_score != null ? ` · ${Math.round(card.quality_score * 100)}% supported` : ""}
              </h3>
              <ul className="mt-2 space-y-1.5 text-sm">
                {card.claims.map((c, i) => (
                  <li key={i} className="flex gap-2">
                    <span className={`shrink-0 text-xs font-medium ${VERDICT[c.verdict] ?? ""}`}>{c.verdict}</span>
                    <span>{c.text}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {card.tags.length > 0 && (
            <div className="mt-6 flex flex-wrap gap-1.5">
              {card.tags.map((t) => (
                <span key={t} className="rounded-full bg-paper px-2 py-0.5 text-xs text-muted">#{t}</span>
              ))}
            </div>
          )}

          <DeeperPanel cardId={card.id} />
        </article>
      )}
    </div>
  );
}
