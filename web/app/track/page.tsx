import { Suspense } from "react";
import TrackInner from "./TrackInner";

export default function Page() {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
      <TrackInner />
    </Suspense>
  );
}
