"use client";

import CardView from "@/components/CardView";
import { Status, useApi } from "@/components/useApi";
import { Card } from "@/lib/api";

export default function SavedPage() {
  const { data, error } = useApi<{ cards: Card[] }>("/api/saves");
  return (
    <div>
      <h1 className="card-title text-3xl font-semibold tracking-tight">Saved</h1>
      <div className="mt-5 space-y-4">
        <Status error={error} loading={!data && !error} />
        {data?.cards.length === 0 && <p className="text-sm text-muted">Nothing saved yet. Tap Save on any card.</p>}
        {data?.cards.map((c) => <CardView key={c.id} card={{ ...c, saved: true }} />)}
      </div>
    </div>
  );
}
