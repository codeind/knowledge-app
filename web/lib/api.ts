// Same origin when the Python server serves the built site (localhost:8000);
// the separate API when running the Next.js dev server (localhost:3000).
export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ??
  (typeof window !== "undefined" && window.location.port === "3000" ? "http://localhost:8000" : "");

export type Source = { id: number; url: string; title: string; publisher: string | null; kind: string; licence: string };
export type Claim = { text: string; passage_ids: number[]; verdict: string };

export type Card = {
  id: number;
  section: "news" | "learn";
  domain: string;
  card_type: string;
  title: string;
  body: string;
  label: "Fact" | "Interpretation" | "Opinion" | "Disputed";
  viewpoint: string | null;
  verification: "verified" | "single_source" | "unverified";
  quality_score: number | null;
  event_date: string | null;
  story_id: number | null;
  origin: "pipeline" | "seed";
  tags: string[];
  entities: { name: string; kind: string }[];
  sources: Source[];
  claims?: Claim[];
  has_depth?: boolean;
  saved?: boolean;
};

export type Book = { id: number; title: string; author: string | null; year: number | null; url: string; public_domain: number };

export type Deeper = {
  card: Card;
  timeline: Card[];
  related: Card[];
  players: Card[];
  explainers: Card[];
  viewpoints: Card[];
  books: Book[];
  has_depth: boolean;
};

export type Track = { domain: string; name: string; cards: number };

export const DOMAIN_NAMES: Record<string, string> = {
  history: "History",
  ancient_history: "Ancient history",
  economics: "Economics",
  sports: "Sports",
  laws_us: "Laws: US",
  laws_in: "Laws: India",
  science: "Science",
  world: "World",
};

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${path}`);
  return res.json() as Promise<T>;
}

export function formatDate(iso: string | null): string {
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m) return iso;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return d ? `${d} ${months[m - 1]} ${y}` : `${months[m - 1]} ${y}`;
}
