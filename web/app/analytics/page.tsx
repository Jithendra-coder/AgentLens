import { Suspense } from "react";
import OverviewClient from "../../components/overview-client";

export default function AnalyticsOverviewPage() {
  return (
    <Suspense fallback={<div className="state">Loading telemetry overview…</div>}>
      <OverviewClient />
    </Suspense>
  );
}
