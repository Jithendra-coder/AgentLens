import { DatasetVersionClient } from "../../../../../components/replay-client";

export default async function DatasetVersionPage({ params }: { params: Promise<{ versionId: string }> }) {
  const { versionId } = await params;
  return <DatasetVersionClient versionId={versionId} />;
}
