import { Suspense } from "react";
import StudioClient from "../components/studio-client";

export default function HomePage() {
  return (
    <Suspense fallback={<div className="state">Loading AI Assistant Studio…</div>}>
      <StudioClient />
    </Suspense>
  );
}
