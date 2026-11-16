"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import CardView from "@/components/CardView";
import { Status, useApi } from "@/components/useApi";
import { Card } from "@/lib/api";

const TYPES = [
  { key: "", label: "All" },
  { key: "concept", label: "Concepts" },
  { key: "event", label: "Events" },
  { key: "law", label: "Laws" },
  { key: "lesson", label: "How it works" },
  { key: "profile", label: "Profiles" },
  { key: "viewpoint", label: "Viewpoints" },
];

export default function TrackInner() {
  const domain = useSearchParams().get("d") ?? "";
  const [type, setType] = useState("");
  const { data, error } = useApi<{ name: string; cards: Card[] }>(domain ? `/api/learn/${domain}${type ? `?card_type=${type}` : ""}` : null);

  return (
    <div>
      <Link href="/learn" className="text-sm text-muted hover:text-accent">← All subjects</Link>
      <h1 className="card-title mt-2 text-3xl font-semibold tracking-tight">{data?.name ?? "…"}</h1>
      {domain.startsWith("laws") && (
        <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
          Plain-language summaries for learning, not legal advice. Check the official text for anything you rely on.
        </p>
      )}
      <div className="mt-5 flex flex-wrap gap-1.5">
        {TYPES.map((t) => (
          <button
            key={t.key || "all"}
            onClick={() => setType(t.key)}
            className={`rounded-full border px-3 py-1 text-xs ${type === t.key ? "border-ink bg-ink text-white" : "border-line text-muted hover:border-accent"}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="mt-5 space-y-4">
        <Status error={error} loading={!data && !error} />
        {data?.cards.length === 0 && <p className="text-sm text-muted">Nothing here yet.</p>}
        {data?.cards.map((c) => <CardView key={c.id} card={c} />)}
      </div>
    </div>
  );
}
