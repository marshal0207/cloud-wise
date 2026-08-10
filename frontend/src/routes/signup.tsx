import { createFileRoute } from "@tanstack/react-router";

import { AuthCard } from "@/components/auth/AuthCard";
import { PageShell } from "@/components/layout/PageShell";

export const Route = createFileRoute("/signup")({
  head: () => ({
    meta: [
      { title: "Sign Up — Start monitoring with CloudWise" },
      {
        name: "description",
        content:
          "Create a free CloudWise account to track cloud resources, usage analytics and estimated cloud costs in one dashboard.",
      },
      { property: "og:title", content: "Sign Up — Start monitoring with CloudWise" },
      {
        property: "og:description",
        content: "Create your CloudWise account and get a cloud monitoring dashboard in minutes.",
      },
    ],
  }),
  component: () => (
    <PageShell withFooter={false}>
      <div className="bg-gradient-soft">
        <AuthCard mode="signup" />
      </div>
    </PageShell>
  ),
});