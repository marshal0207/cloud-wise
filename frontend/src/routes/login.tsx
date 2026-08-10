import { createFileRoute } from "@tanstack/react-router";

import { AuthCard } from "@/components/auth/AuthCard";
import { PageShell } from "@/components/layout/PageShell";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "Login — CloudWise Cloud Management" },
      {
        name: "description",
        content: "Log in to CloudWise to monitor your cloud resources, usage, performance and estimated costs.",
      },
      { property: "og:title", content: "Login — CloudWise Cloud Management" },
      { property: "og:description", content: "Access your CloudWise cloud monitoring dashboard." },
    ],
  }),
  component: () => (
    <PageShell withFooter={false}>
      <div className="bg-gradient-soft">
        <AuthCard mode="login" />
      </div>
    </PageShell>
  ),
});