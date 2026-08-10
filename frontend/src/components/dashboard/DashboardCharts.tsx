import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { buildUsageSeries, formatCurrency, type CloudResource } from "@/lib/cloud-data";

const tooltipStyle = {
  borderRadius: "0.75rem",
  border: "1px solid var(--border)",
  background: "var(--card)",
  color: "var(--card-foreground)",
  fontSize: "0.8rem",
};

const statusColors: Record<string, string> = {
  Active: "var(--success)",
  Warning: "var(--warning)",
  Inactive: "var(--muted-foreground)",
};

export function UsageOverTimeChart({ resources }: { resources: CloudResource[] }) {
  const data = buildUsageSeries(resources);

  return (
    <Card className="rounded-2xl border-border/70 shadow-soft lg:col-span-2">
      <CardHeader className="gap-1">
        <CardTitle className="text-base">Cloud Resource Usage Over Time</CardTitle>
        <p className="text-sm text-muted-foreground">Average utilisation across your resources (%)</p>
      </CardHeader>
      <CardContent className="h-[280px] pl-0">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
            <defs>
              <linearGradient id="usageFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.35} />
                <stop offset="100%" stopColor="var(--primary)" stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id="computeFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--primary-glow)" stopOpacity={0.3} />
                <stop offset="100%" stopColor="var(--primary-glow)" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <XAxis dataKey="label" tickLine={false} axisLine={false} fontSize={12} stroke="var(--muted-foreground)" />
            <YAxis tickLine={false} axisLine={false} fontSize={12} stroke="var(--muted-foreground)" width={34} />
            <Tooltip contentStyle={tooltipStyle} />
            <Area
              type="monotone"
              dataKey="usage"
              name="Overall usage"
              stroke="var(--primary)"
              strokeWidth={2}
              fill="url(#usageFill)"
            />
            <Area
              type="monotone"
              dataKey="compute"
              name="Compute"
              stroke="var(--primary-glow)"
              strokeWidth={2}
              fill="url(#computeFill)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

export function CostDistributionChart({ resources }: { resources: CloudResource[] }) {
  const data = resources.map((resource) => ({
    name: resource.resource_name,
    cost: Number(resource.estimated_cost),
  }));

  return (
    <Card className="rounded-2xl border-border/70 shadow-soft">
      <CardHeader className="gap-1">
        <CardTitle className="text-base">Cost Distribution</CardTitle>
        <p className="text-sm text-muted-foreground">Estimated monthly cost per resource</p>
      </CardHeader>
      <CardContent className="h-[280px] pl-0">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
            <XAxis
              dataKey="name"
              tickLine={false}
              axisLine={false}
              fontSize={11}
              stroke="var(--muted-foreground)"
              interval={0}
              tickFormatter={(value: string) => value.split(" ")[0] ?? value}
            />
            <YAxis tickLine={false} axisLine={false} fontSize={12} stroke="var(--muted-foreground)" width={38} />
            <Tooltip
              contentStyle={tooltipStyle}
              formatter={(value) => formatCurrency(Number(value))}
            />
            <Bar dataKey="cost" name="Estimated cost" fill="var(--primary)" radius={[8, 8, 0, 0]} maxBarSize={44} />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

export function StatusDistributionChart({ resources }: { resources: CloudResource[] }) {
  const counts = resources.reduce<Record<string, number>>((acc, resource) => {
    const key =
      resource.status.toLowerCase() === "active"
        ? "Active"
        : resource.status.toLowerCase() === "warning"
          ? "Warning"
          : "Inactive";
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});

  const data = Object.entries(counts).map(([name, value]) => ({ name, value }));

  return (
    <Card className="rounded-2xl border-border/70 shadow-soft">
      <CardHeader className="gap-1">
        <CardTitle className="text-base">Resource Status</CardTitle>
        <p className="text-sm text-muted-foreground">How your resources are currently behaving</p>
      </CardHeader>
      <CardContent className="h-[280px]">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" innerRadius={58} outerRadius={90} paddingAngle={3}>
              {data.map((entry) => (
                <Cell key={entry.name} fill={statusColors[entry.name] ?? "var(--primary)"} />
              ))}
            </Pie>
            <Tooltip contentStyle={tooltipStyle} />
          </PieChart>
        </ResponsiveContainer>
        <div className="-mt-6 flex flex-wrap justify-center gap-4 text-xs text-muted-foreground">
          {data.map((entry) => (
            <span key={entry.name} className="flex items-center gap-1.5">
              <span
                className="h-2 w-2 rounded-full"
                style={{ background: statusColors[entry.name] ?? "var(--primary)" }}
              />
              {entry.name} ({entry.value})
            </span>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}