"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Card, Deeper, formatDate } from "@/lib/api";
import { Badges } from "./CardView";

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="mt-5">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted">
        {title}
        {hint && <span className="ml-2 font-normal normal-case tracking-normal text-muted/80">{hint}</span>}
      </h3>
      <div className="mt-2">{children}</div>
    </section>
  );
}

function MiniCard({ card }: { card: Card }) {
  return (
    <Link href={`/card/?id=${card.id}`} className="block rounded-xl border border-line bg-paper p-3 hover:border-accent">
      <div className="text-sm font-semibold leading-snug">{card.title}</div>
      <p className="mt-1 line-clamp-3 text-xs leading-relaxed text-muted">{card.body}</p>
    </Link>
  );
}

export default function DeeperPanel({ cardId }: { cardId: number }) {
  const [data, setData] = useState<Deeper | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Deeper>(`/api/cards/${cardId}/deeper`).then(setData).catch((e) => setError(String(e)));
  }, [cardId]);

  if (error) return <p className="mt-4 text-sm text-rose-700">Could not load background: {error}</p>;
  if (!data) return <p className="mt-4 text-sm text-muted">Loading background…</p>;

  const timeline = data.timeline.length > 1 ? data.timeline : [];

  return (
    <div className="mt-5 border-t border-line pt-1">
      {timeline.length > 0 && (
        <Section title="Backstory" hint={`${timeline.length} events, oldest first`}>
          <ol className="relative ml-2 border-l border-line">
            {timeline.map((c) => {
              const current = c.id === data.card.id;
              return (
                <li key={c.id} className="mb-4 ml-4">
                  <span className={`absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full ${current ? "bg-accent" : "bg-line"}`} />
                  <div className="text-xs text-muted">{formatDate(c.event_date)}</div>
                  <Link href={`/card/?id=${c.id}`} className={`text-sm leading-snug hover:text-accent ${current ? "font-semibold" : ""}`}>
                    {c.title}
                  </Link>
                  {current && <span className="ml-2 text-[11px] text-accent">you are here</span>}
                </li>
              );
            })}
          </ol>
        </Section>
      )}

      {data.players.length > 0 && (
        <Section title="Key players">
          <div className="grid gap-2 sm:grid-cols-2">
            {data.players.map((c) => <MiniCard key={c.id} card={c} />)}
          </div>
        </Section>
      )}

      {data.explainers.length > 0 && (
        <Section title="Understand the ideas">
          <div className="grid gap-2 sm:grid-cols-2">
            {data.explainers.map((c) => <MiniCard key={c.id} card={c} />)}
          </div>
        </Section>
      )}

      {data.viewpoints.length > 0 && (
        <Section title="Every side" hint="each written as its supporters would put it">
          <div className="grid gap-2 sm:grid-cols-2">
            {data.viewpoints.map((c) => (
              <div key={c.id} className="rounded-xl border border-amber-200 bg-amber-50/40 p-3">
                <Badges card={c} />
                <div className="mt-2 text-sm font-semibold leading-snug">{c.title}</div>
                <p className="mt-1 text-xs leading-relaxed text-ink/80">{c.body}</p>
              </div>
            ))}
          </div>
        </Section>
      )}

      {data.related.length > 0 && (
        <Section title="Related coverage">
          <ul className="space-y-1.5">
            {data.related.map((c) => (
              <li key={c.id} className="text-sm">
                <span className="text-xs text-muted">{formatDate(c.event_date)} · </span>
                <Link href={`/card/?id=${c.id}`} className="hover:text-accent">{c.title}</Link>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {data.books.length > 0 && (
        <Section title="Books">
          <ul className="space-y-1.5">
            {data.books.map((b) => (
              <li key={b.id} className="flex items-baseline justify-between gap-3 text-sm">
                <a href={b.url} target="_blank" rel="noreferrer" className="hover:text-accent">
                  <span className="card-title italic">{b.title}</span>
                  {b.author && <span className="text-muted"> — {b.author}{b.year ? `, ${b.year}` : ""}</span>}
                </a>
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] ${b.public_domain ? "bg-emerald-50 text-emerald-800" : "bg-paper text-muted"}`}>
                  {b.public_domain ? "Public domain · free to read" : "Title link only"}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}
