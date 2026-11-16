"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!path) return;
    let alive = true;
    setData(null);
    setError(null);
    api<T>(path)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, [path]);

  return { data, error };
}

export function Status({ error, loading }: { error: string | null; loading: boolean }) {
  if (error)
    return (
      <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
        Could not reach the API ({error}). Is the backend running on port 8000?
      </div>
    );
  if (loading) return <p className="text-sm text-muted">Loading…</p>;
  return null;
}
