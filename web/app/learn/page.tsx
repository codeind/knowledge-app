"use client";

import Link from "next/link";
import { Status, useApi } from "@/components/useApi";
import { Track } from "@/lib/api";

const BLURBS: Record<string, string> = {
  history: "Revolutions, wars and turning points, cause and effect.",
  ancient_history: "Early civilisations and empires, and how we know about them.",
  economics: "Core ideas, real examples, and the main schools of thought side by side.",
  sports: "Rules, tactics and the numbers behind the game.",
  laws_us: "How US laws are made, key laws, and bills still in progress.",
  laws_in: "How Indian laws are made, key acts, and new and upcoming changes.",
  science: "Space and science explained simply.",
};

export default function LearnPage() {
  const { data, error } = useApi<{ tracks: Track[] }>("/api/learn/tracks");
  return (
    <div>
      <h1 className="card-title text-3xl font-semibold tracking-tight">Learn</h1>
      <p className="mt-1 text-sm text-muted">Short lessons built only from public-domain and openly licensed sources.</p>
      <div className="mt-6">
        <Status error={error} loading={!data && !error} />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {data?.tracks.map((t) => (
          <Link key={t.domain} href={`/track/?d=${t.domain}`} className="group rounded-2xl border border-line bg-white p-5 hover:border-accent">
            <div className="flex items-baseline justify-between">
              <h2 className="card-title text-lg font-semibold group-hover:text-accent">{t.name}</h2>
              <span className="text-xs text-muted">{t.cards} cards</span>
            </div>
            <p className="mt-1 text-sm text-muted">{BLURBS[t.domain]}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
