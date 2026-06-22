import {
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

import { ProviderBadge } from "@/components/domain/ProviderBadge";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAnomalies, useCostBreakdown, useCostTimeseries } from "@/hooks/useCosts";
import { PROVIDER_META } from "@/lib/constants";
import { formatCurrency, formatDelta } from "@/lib/utils";

export function CostsPage() {
  const breakdown = useCostBreakdown();
  const timeseries = useCostTimeseries(30);
  const anomalies = useAnomalies();

  return (
    <div>
      <PageHeader
        title="Costs"
        description="Full FinOps analytics across providers, services and anomalies."
      />

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="service">By Service</TabsTrigger>
          <TabsTrigger value="anomalies">Anomalies</TabsTrigger>
        </TabsList>

        {/* Overview */}
        <TabsContent value="overview">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <Card className="p-5 lg:col-span-2">
              <h3 className="mb-4 text-h4 font-semibold">Daily spend by provider (30d)</h3>
              {timeseries.isLoading || !timeseries.data ? (
                <Skeleton className="h-72" />
              ) : (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={timeseries.data}>
                    <XAxis dataKey="usage_date" hide />
                    <YAxis
                      tickFormatter={(v) => formatCurrency(v, { compact: true })}
                      tick={{ fontSize: 11, fill: "#94A3B8" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip
                      formatter={(v: number) => formatCurrency(v)}
                      contentStyle={{ borderRadius: 12, fontSize: 12 }}
                    />
                    <Bar dataKey="azure" stackId="a" fill={PROVIDER_META.azure.chartColor} />
                    <Bar dataKey="aws" stackId="a" fill={PROVIDER_META.aws.chartColor} />
                    <Bar
                      dataKey="gcp"
                      stackId="a"
                      fill={PROVIDER_META.gcp.chartColor}
                      radius={[4, 4, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </Card>

            <Card className="p-5">
              <h3 className="mb-4 text-h4 font-semibold">Spend by provider</h3>
              {breakdown.isLoading || !breakdown.data ? (
                <Skeleton className="h-72" />
              ) : (
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart>
                    <Pie
                      data={breakdown.data.by_provider}
                      dataKey="cost_usd"
                      nameKey="provider"
                      innerRadius={60}
                      outerRadius={100}
                      paddingAngle={2}
                    >
                      {breakdown.data.by_provider.map((p) => (
                        <Cell
                          key={p.provider}
                          fill={PROVIDER_META[p.provider].chartColor}
                        />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v: number) => formatCurrency(v)} />
                  </PieChart>
                </ResponsiveContainer>
              )}
              <div className="mt-2 space-y-1">
                {breakdown.data?.by_provider.map((p) => (
                  <div
                    key={p.provider}
                    className="flex items-center justify-between text-body-sm"
                  >
                    <ProviderBadge provider={p.provider} size="sm" />
                    <span className="tabular-nums text-neutral-500">
                      {p.pct_of_total}%
                    </span>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </TabsContent>

        {/* By Service */}
        <TabsContent value="service">
          <Card className="overflow-hidden">
            <table className="w-full text-body-sm">
              <thead className="border-b border-neutral-200 bg-neutral-50">
                <tr className="text-left text-caption uppercase text-neutral-400">
                  <th className="px-5 py-3">Service</th>
                  <th className="px-5 py-3">Provider</th>
                  <th className="px-5 py-3 text-right">MTD cost</th>
                  <th className="px-5 py-3 text-right">vs last month</th>
                  <th className="px-5 py-3 text-right">% of total</th>
                </tr>
              </thead>
              <tbody>
                {(breakdown.data?.by_service ?? []).map((s, i) => (
                  <tr key={i} className="border-b border-neutral-100 hover:bg-neutral-50">
                    <td className="px-5 py-3 font-medium text-neutral-900">{s.service}</td>
                    <td className="px-5 py-3">
                      <ProviderBadge provider={s.provider} size="sm" />
                    </td>
                    <td className="px-5 py-3 text-right tabular-nums">
                      {formatCurrency(s.cost_usd)}
                    </td>
                    <td
                      className={`px-5 py-3 text-right tabular-nums ${
                        s.vs_last_month_pct > 0 ? "text-status-danger" : "text-status-success"
                      }`}
                    >
                      {formatDelta(s.vs_last_month_pct)}
                    </td>
                    <td className="px-5 py-3 text-right tabular-nums text-neutral-500">
                      {s.pct_of_total}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </TabsContent>

        {/* Anomalies */}
        <TabsContent value="anomalies">
          <div className="space-y-3">
            {(anomalies.data ?? []).map((a, i) => (
              <Card key={i} className="flex items-center gap-4 p-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-status-danger/10 text-status-danger">
                  ▲
                </div>
                <div className="flex-1">
                  <p className="text-body-sm font-semibold text-neutral-900">
                    {a.service} spike on {a.usage_date}
                  </p>
                  <p className="text-caption text-neutral-500">
                    Expected {formatCurrency(a.expected_usd)} · actual{" "}
                    {formatCurrency(a.actual_usd)}
                  </p>
                </div>
                <div className="text-right">
                  <ProviderBadge provider={a.provider} size="sm" />
                  <p className="mt-1 text-body-sm font-semibold text-status-danger">
                    +{formatCurrency(a.delta_usd)} ({a.delta_pct}%)
                  </p>
                </div>
              </Card>
            ))}
            {!anomalies.data?.length && (
              <Card className="p-8 text-center text-body-sm text-neutral-500">
                No anomalies detected. The CostAgent runs hourly.
              </Card>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
