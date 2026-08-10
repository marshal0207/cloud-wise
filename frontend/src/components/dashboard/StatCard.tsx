import type { LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

export function StatCard({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <Card className="rounded-2xl border-border/70 bg-gradient-card shadow-soft transition-shadow hover:shadow-lift">
      <CardContent className="p-5">
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
          <p className="min-w-0 truncate text-sm font-medium text-muted-foreground">{label}</p>
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
            <Icon className="h-4.5 w-4.5" />
          </span>
        </div>
        <p className="mt-3 text-2xl font-bold tracking-tight">{value}</p>
        <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  );
}