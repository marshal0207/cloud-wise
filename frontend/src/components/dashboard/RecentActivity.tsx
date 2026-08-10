import { Activity } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { buildActivity, type CloudResource } from "@/lib/cloud-data";

const toneStyles: Record<string, string> = {
  info: "bg-primary",
  warn: "bg-warning",
  muted: "bg-muted-foreground",
};

export function RecentActivity({ resources }: { resources: CloudResource[] }) {
  const items = buildActivity(resources);

  return (
    <Card className="rounded-2xl border-border/70 shadow-soft">
      <CardHeader className="gap-1">
        <CardTitle className="flex items-center gap-2 text-base">
          <Activity className="h-4 w-4 shrink-0 text-primary" /> Recent Activity
        </CardTitle>
        <p className="text-sm text-muted-foreground">Latest events across your cloud environment</p>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">No activity recorded yet.</p>
        ) : (
          <ul className="space-y-4">
            {items.map((item) => (
              <li key={item.id} className="flex gap-3">
                <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${toneStyles[item.tone]}`} />
                <div className="min-w-0">
                  <p className="text-sm">{item.text}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{item.when}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}