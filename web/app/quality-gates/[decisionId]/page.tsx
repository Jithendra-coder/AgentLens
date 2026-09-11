import { QualityGateDetailClient } from "../../../components/quality-gates-client";

export default async function QualityGateDetailPage({ params }: { params: Promise<{ decisionId: string }> }) {
  const { decisionId } = await params;
  return <QualityGateDetailClient decisionId={decisionId} />;
}
