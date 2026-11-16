import { Suspense } from "react";
import CardInner from "./CardInner";

export default function Page() {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
      <CardInner />
    </Suspense>
  );
}
