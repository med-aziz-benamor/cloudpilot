import { AlertTriangle } from "lucide-react";
import { useState } from "react";

import { ForecastChart } from "@/components/domain/ForecastChart";
import { MetricCard } from "@/components/domain/MetricCard";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/domain/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { useForecast } from "@/hooks/useForecast";
import { formatCurrency } from "@/lib/utils";

export function ForecastPage() {
  const [horizon, setHorizon] = useState<30 | 60 | 90>(30);
  const { data, isLoading, isError } = useForecast(horizon);

  return (
    <div className="no-print:overflow-visible">
      <PageHeader
        title="Forecast"
        description="Predictive cloud spend powered by the ForecastAgent (Prophet)."
        actions={
          <div className="flex gap-1 rounded-lg bg-neutral-100 p-1 no-print">
            {([30, 60, 90] as const).map((h) => (
              <button
                key={h}
                onClick={() => setHorizon(h)}
                className={`rounded-md px-3 py-1 text-body-sm font-medium ${
                  horizon === h ? "bg-white text-neutral-900 shadow-sm" : "text-neutral-500"
                }`}
              >
                {h}d
              </button>
            ))}
          </div>
        }
      />

      {isError ? (
        <EmptyState
          icon={AlertTriangle}
          title="No forecast available yet"
          description="The ForecastAgent runs daily at 03:00 UTC. Run it from the command palette (⌘K → Run ForecastAgent) to generate one now."
        />
      ) : isLoading || !data ? (
        <div className="space-y-4">
          <div className="grid grid-cols-4 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-28" />
            ))}
          </div>
          <Skeleton className="h-96" />
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Current MTD"
              value={data.current_mtd_usd}
              format={(v) => formatCurrency(v)}
            />
            <MetricCard
              label="Projected month-end"
              value={data.projected_month_end_usd}
              format={(v) => formatCurrency(v)}
              sublabel={data.over_budget ? "Over budget" : "Within budget"}
            />
            <MetricCard
              label="Budget"
              value={data.budget_usd}
              format={(v) => formatCurrency(v)}
            />
            <MetricCard
              label="Next 90 days"
              value={data.next_90d_usd}
              format={(v) => formatCurrency(v, { compact: true })}
            />
          </div>

          <Card className="p-5">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-h3 font-semibold">Spend forecast</h2>
              {data.over_budget && (
                <Badge variant="danger">
                  <AlertTriangle size={12} /> OVER BUDGET +{data.overrun_pct}%
                </Badge>
              )}
            </div>
            <ForecastChart forecast={data} />
          </Card>

          <Card className="p-5 no-print">
            <h3 className="mb-3 text-h4 font-semibold">Budget alerts</h3>
            <p className="mb-3 text-caption text-neutral-400">
              Set via seed data — editing isn't available yet.
            </p>
            <div className="flex flex-wrap items-center gap-6 text-body-sm text-neutral-600">
              <label className="flex items-center gap-2">
                Monthly budget
                <input
                  type="number"
                  defaultValue={data.budget_usd}
                  disabled
                  className="w-28 rounded-md border border-neutral-200 px-2 py-1 disabled:cursor-not-allowed disabled:bg-neutral-50 disabled:text-neutral-400"
                />
              </label>
              <span className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-status-warning" /> Warning at 80%
              </span>
              <span className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-status-danger" /> Danger at 100%
              </span>
              <label className="flex items-center gap-2 text-neutral-400">
                <input type="checkbox" defaultChecked disabled /> Alert on projected overrun
              </label>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
