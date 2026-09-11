import { RegressionDetailClient } from "../../../components/regressions-client";

export default async function RegressionDetailPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  return <RegressionDetailClient runId={runId} />;
}
