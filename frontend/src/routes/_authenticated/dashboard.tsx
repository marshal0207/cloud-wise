import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Activity, CircleDollarSign, Gauge, RefreshCw, Server } from "lucide-react";

import { PageShell } from "@/components/layout/PageShell";
import {
  CostDistributionChart,
  StatusDistributionChart,
  UsageOverTimeChart,
} from "@/components/dashboard/DashboardCharts";
import { RecentActivity } from "@/components/dashboard/RecentActivity";
import { ResourceTable } from "@/components/dashboard/ResourceTable";
import { StatCard } from "@/components/dashboard/StatCard";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/hooks/use-auth";
import { formatCurrency, type CloudResource } from "@/lib/cloud-data";
import { supabase } from "@/integrations/supabase/client";

export const Route = createFileRoute("/_authenticated/dashboard")({
  head: () => ({
    meta: [
      { title: "Dashboard — CloudWise cloud monitoring" },
      {
        name: "description",
        content:
          "Monitor your cloud resources, usage trends, resource status and estimated costs from the CloudWise dashboard.",
      },
      { property: "og:title", content: "Dashboard — CloudWise cloud monitoring" },
      {
        property: "og:description",
        content: "Your cloud resources, usage analytics and estimated costs in one place.",
      },
    ],
  }),
  component: DashboardPage,
});

function DashboardPage() {
  const { displayName } = useAuth();

  const { data, isLoading, isError, refetch, isFetching, dataUpdatedAt } = useQuery({
    queryKey: ["cloud_resources"],
    queryFn: async (): Promise<CloudResource[]> => {
      const { data: rows, error } = await supabase
        .from("cloud_resources")
        .select("id, resource_name, resource_type, status, usage, region, estimated_cost, last_updated")
        .order("created_at", { ascending: true });
      if (error) throw error;
      return (rows ?? []) as CloudResource[];
    },
  });

  const resources = data ?? [];
  const active = resources.filter((r) => r.status.toLowerCase() === "active").length;
  const averageUsage =
    resources.length > 0
      ? Math.round(resources.reduce((sum, r) => sum + Number(r.usage), 0) / resources.length)
      : 0;
  const totalCost = resources.reduce((sum, r) => sum + Number(r.estimated_cost), 0);

  return (
    <PageShell>
      <div className="bg-gradient-soft">
        <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 lg:py-12">
          <header className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-4 sm:flex sm:flex-wrap sm:items-center sm:justify-between">
            <div className="min-w-0">
              <h1 className="truncate text-2xl font-bold tracking-tight sm:text-3xl">
                Welcome to CloudWise, {displayName}
              </h1>
              <p className="mt-1.5 text-sm text-muted-foreground">
                A quick overview of your cloud resources, usage and estimated spend.
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Last updated{" "}
                {dataUpdatedAt
                  ? new Date(dataUpdatedAt).toLocaleString(undefined, {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })
                  : "—"}
              </p>
            </div>
            <Button
              variant="outline"
              className="shrink-0 rounded-xl"
              onClick={() => void refetch()}
              disabled={isFetching}
            >
              <RefreshCw className={`mr-2 h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </header>

          {isError ? (
            <div className="mt-8 rounded-2xl border border-destructive/30 bg-destructive/10 p-6 text-sm">
              <p className="font-medium">We couldn't load your cloud resources.</p>
              <p className="mt-1 text-muted-foreground">Please check your connection and try again.</p>
              <Button variant="outline" className="mt-4 rounded-xl" onClick={() => void refetch()}>
                Try again
              </Button>
            </div>
          ) : isLoading ? (
            <div className="mt-8 space-y-6">
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {[0, 1, 2, 3].map((key) => (
                  <Skeleton key={key} className="h-[132px] rounded-2xl" />
                ))}
              </div>
              <div className="grid gap-6 lg:grid-cols-3">
                <Skeleton className="h-[340px] rounded-2xl lg:col-span-2" />
                <Skeleton className="h-[340px] rounded-2xl" />
              </div>
              <Skeleton className="h-[300px] rounded-2xl" />
            </div>
          ) : (
            <>
              <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <StatCard
                  icon={Server}
                  label="Total Resources"
                  value={String(resources.length)}
                  hint="Tracked in your workspace"
                />
                <StatCard
                  icon={Activity}
                  label="Active Resources"
                  value={String(active)}
                  hint={`${resources.length - active} need attention`}
                />
                <StatCard
                  icon={Gauge}
                  label="Cloud Usage"
                  value={`${averageUsage}%`}
                  hint="Average utilisation"
                />
                <StatCard
                  icon={CircleDollarSign}
                  label="Estimated Cost"
                  value={formatCurrency(totalCost)}
                  hint="Projected this month"
                />
              </div>

              <div className="mt-6 grid gap-6 lg:grid-cols-3">
                <UsageOverTimeChart resources={resources} />
                <StatusDistributionChart resources={resources} />
                <CostDistributionChart resources={resources} />
                <div className="lg:col-span-2">
                  <RecentActivity resources={resources} />
                </div>
              </div>

              <div className="mt-6">
                <ResourceTable resources={resources} />
              </div>

              <p className="mt-6 text-xs text-muted-foreground">
                Values shown are demo data stored in your CloudWise account. Live provider metrics can be
                connected later without changing this dashboard.
              </p>
            </>
          )}
        </div>
      </div>
    </PageShell>
  );
}