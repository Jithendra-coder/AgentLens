import EvaluationDetailClient from "../../../components/evaluation-detail-client";

export default async function EvaluationDetailPage({ params }: { params: Promise<{ resultId: string }> }) {
  const { resultId } = await params;
  return <EvaluationDetailClient resultId={resultId} />;
}
