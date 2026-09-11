import SystemHealthClient from "../../components/system-health";

export const metadata = {
  title: "System Health | AgentLens",
  description: "Internal platform observability, latency distributions, and worker telemetry",
};

export default function SystemHealthPage() {
  return <SystemHealthClient />;
}
