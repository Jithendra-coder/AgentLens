import { Suspense } from "react";
import RagLensClient from "../../components/raglens-client";

export default function RagLensPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-xs text-slate-500">Loading RagLens Studio…</div>}>
      <RagLensClient />
    </Suspense>
  );
}
