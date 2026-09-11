import type { Metadata } from "next";
import "./globals.css";
import { Sidebar, TopHeader } from "../components/ui";

export const metadata: Metadata = {
  title: "AgentLens — AI Observability Platform",
  description: "Enterprise AI Agent Observability, Quality Evaluation & Governance Platform",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <div className="app-layout">
          <Sidebar />
          <div className="app-viewport">
            <TopHeader />
            <main className="main">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
