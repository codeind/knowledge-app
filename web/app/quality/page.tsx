"use client";

import { Status, useApi } from "@/components/useApi";

type Stats = {
  cards_by_status: Record<string, number>;
  published_by_domain: Record<string, number>;
  claim_verdicts: Record<string, number>;
  claim_support_rate: number | null;
  stories: number;
  links: number;
  books: number;
  recent_runs: { job: string; started_at: string; cards_drafted: number; cards_published: number; cards_rejected: number }[];
};

function Tile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-line bg-white p-4">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

export default function QualityPage() {
  const { data, error } = useApi<Stats>("/api/stats");
  return (
    <div>
      <h1 className="card-title text-3xl font-semibold tracking-tight">Content quality</h1>
      <p className="mt-1 text-sm text-muted">How the pipeline is doing: what was published, what the verifier rejected, and why.</p>
      <div className="mt-5">
        <Status error={error} loading={!data && !error} />
      </div>
      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Tile label="Published cards" value={data.cards_by_status.published ?? 0} />
            <Tile label="Rejected by verifier" value={data.cards_by_status.rejected ?? 0} />
            <Tile label="Claims supported" value={data.claim_support_rate == null ? "—" : `${Math.round(data.claim_support_rate * 100)}%`} />
            <Tile label="Story threads" value={data.stories} />
          </div>

          <h2 className="mt-8 text-xs font-semibold uppercase tracking-wider text-muted">Published by section</h2>
          <table className="mt-2 w-full text-sm">
            <tbody>
              {Object.entries(data.published_by_domain).map(([k, v]) => (
                <tr key={k} className="border-b border-line">
                  <td className="py-1.5">{k.replace(":", " · ").replace("_", " ")}</td>
                  <td className="py-1.5 text-right tabular-nums">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h2 className="mt-8 text-xs font-semibold uppercase tracking-wider text-muted">Recent pipeline runs</h2>
          {data.recent_runs.length === 0 ? (
            <p className="mt-2 text-sm text-muted">No runs yet. Only sample cards are loaded.</p>
          ) : (
            <table className="mt-2 w-full text-sm">
              <thead className="text-left text-xs text-muted">
                <tr>
                  <th className="py-1">Job</th>
                  <th>Started</th>
                  <th className="text-right">Drafted</th>
                  <th className="text-right">Published</th>
                  <th className="text-right">Rejected</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_runs.map((r, i) => (
                  <tr key={i} className="border-b border-line">
                    <td className="py-1.5">{r.job}</td>
                    <td>{r.started_at}</td>
                    <td className="text-right tabular-nums">{r.cards_drafted}</td>
                    <td className="text-right tabular-nums">{r.cards_published}</td>
                    <td className="text-right tabular-nums">{r.cards_rejected}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
