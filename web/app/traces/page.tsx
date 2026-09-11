import { Suspense } from "react";
import TracesClient from "../../components/traces-client";

export default function TracesPage() {
  return (
    <Suspense fallback={<div className="state"><p>Loading traces...</p></div>}>
      <TracesClient />
    </Suspense>
  );
}

