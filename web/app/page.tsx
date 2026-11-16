"use client";

import { useState } from "react";
import CardView from "@/components/CardView";
import { Status, useApi } from "@/components/useApi";
import { Card, DOMAIN_NAMES } from "@/lib/api";

const FILTERS = ["", "science", "economics", "laws_us", "laws_in", "sports", "history"];

export default function NewsPage() {
  const [domain, setDomain] = useState("");
  const { data, error } = useApi<{ cards: Card[] }>(`/api/news?limit=40${domain ? `&domain=${domain}` : ""}`);

  return (
    <div>
      <h1 className="card-title text-3xl font-semibold tracking-tight">News, with the background</h1>
      <p className="mt-1 text-sm text-muted">Tap Go deeper on a story to see what led up to it, who is involved, and the ideas behind it.</p>

      <div className="mt-5 flex flex-wrap gap-1.5">
        {FILTERS.map((d) => (
          <button
            key={d || "all"}
            onClick={() => setDomain(d)}
            className={`rounded-full border px-3 py-1 text-xs ${domain === d ? "border-ink bg-ink text-white" : "border-line text-muted hover:border-accent"}`}
          >
            {d ? DOMAIN_NAMES[d] : "All"}
          </button>
        ))}
      </div>

      <div className="mt-5 space-y-4">
        <Status error={error} loading={!data && !error} />
        {data?.cards.length === 0 && <p className="text-sm text-muted">No stories yet. Run the pipeline to add some.</p>}
        {data?.cards.map((card) => <CardView key={card.id} card={card} />)}
      </div>
    </div>
  );
}
