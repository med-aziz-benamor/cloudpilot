import { Cloud, DollarSign, Lightbulb, PiggyBank } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { AgentBadge } from "@/components/domain/AgentBadge";
import { CostBreakdownChart } from "@/components/domain/CostBreakdownChart";
import { MetricCard } from "@/components/domain/MetricCard";
import { OptimizationScore } from "@/components/domain/OptimizationScore";
import { ProviderBadge } from "@/components/domain/ProviderBadge";
import { SparklineChart } from "@/components/domain/SparklineChart";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useCloudAccounts } from "@/hooks/useCloudAccounts";
import {
  useCostSummary,
  useCostTimeseries,
  useTopDrivers,
} from "@/hooks/useCosts";
import { useRecommendations } from "@/hooks/useRecommendations";
import { useCloudStore } from "@/stores/cloud.store";
import { formatCurrency, greeting } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth.store";

export function OverviewPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const { timeRange, setTimeRange } = useCloudStore();
  const summary = useCostSummary();
  const timeseries = useCostTimeseries(timeRange);
  const drivers = useTopDrivers(5);
  const recs = useRecommendations({ status: "pending", sort: "impact" });
  const accounts = useCloudAccounts();

  const totalSpark = (timeseries.data ?? []).slice(-7).map((p) => p.total);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-h1 font-bold text-neutral-900">
            {greeting()}, {user?.full_name?.split(" ")[0] ?? "there"} 👋
          </h1>
          <p className="mt-1 text-body text-neutral-500">
            {new Date().toLocaleDateString("en-US", {
              weekday: "long",
              month: "long",
              day: "numeric",
            })}{" "}
            · Last synced 2 min ago
          </p>
        </div>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {summary.isLoading || !summary.data ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-40" />
          ))
        ) : (
          <>
            <MetricCard
              label="Monthly Spend (MTD)"
              value={summary.data.mtd_usd}
              format={(v) => formatCurrency(v)}
              delta={summary.data.delta_pct}
              deltaIsGood={(d) => d <= 0}
              icon={DollarSign}
              sparkline={totalSpark}
            />
            <MetricCard
              label="Potential Savings"
              value={summary.data.potential_savings_usd}
              format={(v) => formatCurrency(v)}
              icon={PiggyBank}
              sparklineColor="#10B981"
              sublabel={`${summary.data.pending_recommendations} recommendations`}
            />
            <Card className="flex items-center justify-between p-5">
              <div>
                <p className="text-label uppercase text-neutral-400">
                  Optimization Score
                </p>
                <p className="mt-2 text-body-sm text-neutral-500">
                  Cloud health index
                </p>
              </div>
              <OptimizationScore score={summary.data.optimization_score} size={88} />
            </Card>
            <MetricCard
              label="Connected Clouds"
              value={summary.data.connected_clouds}
              format={(v) => String(Math.round(v))}
              icon={Cloud}
              sublabel="Azure · AWS · GCP"
            />
          </>
        )}
      </div>

      {/* Spend chart */}
      <Card className="p-5">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-h3 font-semibold text-neutral-900">
              Multi-Cloud Spend
            </h2>
            <p className="text-body-sm text-neutral-500">
              Daily spend across all providers
            </p>
          </div>
          <div className="flex gap-1 rounded-lg bg-neutral-100 p-1">
            {([7, 30, 90] as const).map((d) => (
              <button
                key={d}
                onClick={() => setTimeRange(d)}
                className={`rounded-md px-3 py-1 text-body-sm font-medium transition-colors ${
                  timeRange === d
                    ? "bg-white text-neutral-900 shadow-sm"
                    : "text-neutral-500"
                }`}
              >
                {d}d
              </button>
            ))}
          </div>
        </div>
        {timeseries.isLoading || !timeseries.data ? (
          <Skeleton className="h-80" />
        ) : (
          <CostBreakdownChart data={timeseries.data} />
        )}
      </Card>

      {/* Bottom grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Top cost drivers */}
        <Card className="p-5">
          <h2 className="mb-4 text-h3 font-semibold text-neutral-900">
            Top Cost Drivers
          </h2>
          <div className="space-y-1">
            {(drivers.data ?? []).map((d) => (
              <button
                key={d.resource_id}
                onClick={() => navigate("/resources")}
                className="flex w-full items-center gap-3 rounded-md px-2 py-2 text-left transition-colors hover:bg-neutral-50"
              >
                <ProviderBadge provider={d.provider} size="sm" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-mono text-body-sm text-neutral-900">
                    {d.name}
                  </p>
                  <p className="text-caption text-neutral-400">
                    {d.service.replace(/_/g, " ")}
                  </p>
                </div>
                <div className="hidden w-16 sm:block">
                  <SparklineChart data={d.trend} height={28} />
                </div>
                <span className="text-body-sm font-semibold tabular-nums">
                  {formatCurrency(d.monthly_cost_usd)}
                </span>
              </button>
            ))}
          </div>
        </Card>

        {/* AI insights feed */}
        <Card className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-h3 font-semibold text-neutral-900">AI Insights</h2>
            <button
              onClick={() => navigate("/recommendations")}
              className="text-body-sm font-medium text-brand-primary hover:underline"
            >
              View all →
            </button>
          </div>
          <div className="space-y-3">
            {(recs.data ?? []).slice(0, 3).map((r) => (
              <div
                key={r.id}
                className="rounded-lg border border-neutral-100 p-3"
                style={{ borderLeft: `3px solid var(--tw-shadow-color, #0D6EFD)` }}
              >
                <AgentBadge agent={r.agent} />
                <p className="mt-2 text-body-sm font-medium text-neutral-900">
                  {r.title}
                </p>
                {r.estimated_saving_usd ? (
                  <p className="mt-1 text-body-sm font-semibold text-status-success">
                    Save {formatCurrency(r.estimated_saving_usd)}/mo
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Provider status strip */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {(accounts.data ?? []).map((a) => (
          <Card key={a.id} className="flex items-center gap-3 p-4">
            <ProviderBadge provider={a.provider} size="sm" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-body-sm font-medium text-neutral-900">
                {a.display_name}
              </p>
              <p className="text-caption text-neutral-400">
                {a.resource_count} resources ·{" "}
                {formatCurrency(a.monthly_cost_usd, { compact: true })}
              </p>
            </div>
            <span className="flex items-center gap-1 text-caption text-status-success">
              <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-status-success" />
              Connected
            </span>
          </Card>
        ))}
        {!accounts.data?.length && (
          <Card className="col-span-3 flex items-center gap-3 p-4">
            <Lightbulb size={18} className="text-neutral-400" />
            <p className="text-body-sm text-neutral-500">
              No cloud accounts yet — run <code>make seed</code> for demo data.
            </p>
          </Card>
        )}
      </div>
    </div>
  );
}
