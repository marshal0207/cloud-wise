export type CloudResource = {
  id: string;
  resource_name: string;
  resource_type: string;
  status: string;
  usage: number;
  region: string;
  estimated_cost: number;
  last_updated: string;
};

/**
 * Demo usage history. Replace this with a real provider metrics call
 * (CloudWatch / Azure Monitor / GCP Monitoring) when an integration is added.
 */
export function buildUsageSeries(resources: CloudResource[]) {
  const average =
    resources.length > 0
      ? resources.reduce((sum, r) => sum + Number(r.usage), 0) / resources.length
      : 45;

  const offsets = [-14, -9, -4, 2, -3, 6, 3, 9, 5, 11, 7, 12];
  const now = new Date();

  return offsets.map((offset, index) => {
    const date = new Date(now);
    date.setDate(now.getDate() - (offsets.length - 1 - index) * 2);
    const usage = Math.max(5, Math.min(99, Math.round(average + offset)));
    return {
      label: date.toLocaleDateString(undefined, { month: "short", day: "numeric" }),
      usage,
      compute: Math.max(4, Math.min(99, Math.round(usage * 0.72))),
      storage: Math.max(3, Math.min(99, Math.round(usage * 0.48))),
    };
  });
}

export function statusMeta(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "active") {
    return { label: "Active", dot: "bg-success", chip: "bg-success/12 text-success border-success/30" };
  }
  if (normalized === "warning") {
    return { label: "Warning", dot: "bg-warning", chip: "bg-warning/15 text-warning-foreground border-warning/40" };
  }
  return {
    label: "Inactive",
    dot: "bg-muted-foreground",
    chip: "bg-muted text-muted-foreground border-border",
  };
}

export function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
}

export function buildActivity(resources: CloudResource[]) {
  if (resources.length === 0) return [];
  const templates = [
    { tone: "info" as const, text: (name: string) => `${name} health check completed successfully` },
    { tone: "warn" as const, text: (name: string) => `${name} crossed 80% sustained usage` },
    { tone: "info" as const, text: (name: string) => `Usage metrics refreshed for ${name}` },
    { tone: "muted" as const, text: (name: string) => `${name} was scaled down to reduce cost` },
  ];

  return resources.slice(0, 4).map((resource, index) => {
    const template = templates[index % templates.length]!;
    return {
      id: resource.id,
      tone: template.tone,
      text: template.text(resource.resource_name),
      when: `${(index + 1) * 12} minutes ago`,
    };
  });
}