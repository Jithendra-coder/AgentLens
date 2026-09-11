import SettingsClient from "../../components/settings-client";

export const metadata = {
  title: "Project Settings & RBAC | AgentLens",
  description: "Manage project isolation, team membership, Role-Based Access Control, and API keys",
};

export default function SettingsPage() {
  return <SettingsClient />;
}
