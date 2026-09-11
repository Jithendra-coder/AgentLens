import { ReplayDetailClient } from "../../../components/replay-client";

export default async function ReplayDetailPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return <ReplayDetailClient runId={runId} />;
}
