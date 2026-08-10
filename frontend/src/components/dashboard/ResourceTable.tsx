import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "./StatusBadge";
import { formatCurrency, type CloudResource } from "@/lib/cloud-data";

export function ResourceTable({ resources }: { resources: CloudResource[] }) {
  return (
    <Card className="rounded-2xl border-border/70 shadow-soft">
      <CardHeader className="gap-1">
        <CardTitle className="text-base">Cloud Resources</CardTitle>
        <p className="text-sm text-muted-foreground">
          All resources currently tracked in your CloudWise workspace.
        </p>
      </CardHeader>
      <CardContent className="p-0 pb-2">
        {resources.length === 0 ? (
          <p className="px-6 py-10 text-center text-sm text-muted-foreground">
            No cloud resources yet. Once resources are added they will appear here.
          </p>
        ) : (
          <>
            {/* Desktop / tablet: scrollable table */}
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full min-w-[860px] text-sm">
                <thead>
                  <tr className="border-y border-border bg-secondary/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="px-6 py-3 font-semibold">Resource</th>
                    <th className="px-4 py-3 font-semibold">Type</th>
                    <th className="px-4 py-3 font-semibold">Status</th>
                    <th className="px-4 py-3 font-semibold">Usage</th>
                    <th className="px-4 py-3 font-semibold">Region</th>
                    <th className="px-4 py-3 font-semibold">Est. cost</th>
                    <th className="px-6 py-3 font-semibold">Last updated</th>
                  </tr>
                </thead>
                <tbody>
                  {resources.map((resource) => (
                    <tr key={resource.id} className="border-b border-border/70 transition-colors hover:bg-secondary/40">
                      <td className="px-6 py-3.5 font-medium">{resource.resource_name}</td>
                      <td className="px-4 py-3.5 text-muted-foreground">{resource.resource_type}</td>
                      <td className="px-4 py-3.5">
                        <StatusBadge status={resource.status} />
                      </td>
                      <td className="px-4 py-3.5">
                        <div className="flex items-center gap-2">
                          <span className="h-1.5 w-20 overflow-hidden rounded-full bg-secondary">
                            <span
                              className="block h-full rounded-full bg-gradient-hero"
                              style={{ width: `${Math.min(100, Number(resource.usage))}%` }}
                            />
                          </span>
                          <span className="text-xs text-muted-foreground">{Number(resource.usage)}%</span>
                        </div>
                      </td>
                      <td className="px-4 py-3.5 text-muted-foreground">{resource.region}</td>
                      <td className="px-4 py-3.5 font-medium">{formatCurrency(Number(resource.estimated_cost))}</td>
                      <td className="px-6 py-3.5 text-muted-foreground">
                        {new Date(resource.last_updated).toLocaleString(undefined, {
                          dateStyle: "medium",
                          timeStyle: "short",
                        })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile: stacked cards */}
            <ul className="divide-y divide-border md:hidden">
              {resources.map((resource) => (
                <li key={resource.id} className="px-5 py-4">
                  <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
                    <p className="min-w-0 truncate font-medium">{resource.resource_name}</p>
                    <StatusBadge status={resource.status} />
                  </div>
                  <dl className="mt-3 grid grid-cols-2 gap-y-2 text-xs">
                    <dt className="text-muted-foreground">Type</dt>
                    <dd className="text-right">{resource.resource_type}</dd>
                    <dt className="text-muted-foreground">Usage</dt>
                    <dd className="text-right">{Number(resource.usage)}%</dd>
                    <dt className="text-muted-foreground">Region</dt>
                    <dd className="text-right">{resource.region}</dd>
                    <dt className="text-muted-foreground">Est. cost</dt>
                    <dd className="text-right">{formatCurrency(Number(resource.estimated_cost))}</dd>
                    <dt className="text-muted-foreground">Updated</dt>
                    <dd className="text-right">
                      {new Date(resource.last_updated).toLocaleDateString(undefined, { dateStyle: "medium" })}
                    </dd>
                  </dl>
                </li>
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}