import { AlertTriangle, ShieldCheck } from "lucide-react";

import { ProviderBadge } from "@/components/domain/ProviderBadge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { usePricingCatalog } from "@/hooks/usePricing";
import { formatAsOf, formatRate, PRICE_SOURCE_META } from "@/lib/pricing";

/**
 * The rate card itself — every SKU CloudPilot can price, and where each rate
 * came from.
 *
 * This is the reference behind the per-recommendation derivations: a reviewer who
 * wants to check one saving reads it on the card, and one who wants to know how
 * defensible the platform's numbers are as a whole reads it here.
 */
export function RateCardPanel() {
  const { data, isLoading, isError } = usePricingCatalog();

  if (isLoading) return <Skeleton className="h-64" />;
  if (isError || !data) {
    return (
      <Card className="p-5 text-body-sm text-neutral-400">
        The pricing catalog could not be loaded.
      </Card>
    );
  }

  const regions = Object.entries(data.regions)
    .map(([provider, region]) => `${provider} ${region}`)
    .join(" · ");

  return (
    <div className="space-y-4">
      <Card className="p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h3 className="text-h4 font-semibold text-neutral-900">Rate card</h3>
            <p className="mt-1 text-body-sm text-neutral-500">
              {data.total_count} SKUs, quoted as of {formatAsOf(data.generated_at)}
              {data.age_days > 0 && ` (${data.age_days} days ago)`}.
            </p>
            {regions && (
              <p className="mt-0.5 font-mono text-caption text-neutral-400">{regions}</p>
            )}
          </div>
          <div className="text-right">
            <p className="text-h3 font-semibold tabular-nums text-neutral-900">
              {data.api_verified_pct.toFixed(0)}%
            </p>
            <p className="text-caption text-neutral-500">
              {data.api_verified_count} of {data.total_count} API-verified
            </p>
          </div>
        </div>

        {data.is_stale && (
          <p className="mt-4 flex items-start gap-2 rounded-md bg-status-warning/10 p-3 text-body-sm text-[#92400E]">
            <AlertTriangle size={15} className="mt-0.5 shrink-0" aria-hidden />
            <span>
              This snapshot is older than {data.stale_after_days} days. Providers
              revise list prices a few times a year, so savings derived from it may
              no longer match what is billed. Refresh it with{" "}
              <code className="font-mono">make pricing</code>.
            </span>
          </p>
        )}
      </Card>

      <Card className="overflow-x-auto">
        <table className="w-full text-body-sm">
          <thead className="border-b border-neutral-200 bg-neutral-50 text-left text-caption uppercase text-neutral-400">
            <tr>
              <th className="px-5 py-3">SKU</th>
              <th className="px-5 py-3">Cloud</th>
              <th className="px-5 py-3 text-right">Rate</th>
              <th className="px-5 py-3">Region</th>
              <th className="px-5 py-3">Source</th>
              <th className="px-5 py-3">Meter</th>
            </tr>
          </thead>
          <tbody>
            {data.rates.map((rate) => {
              const meta = PRICE_SOURCE_META[rate.source];
              return (
                <tr key={`${rate.provider}-${rate.sku}`} className="border-b border-neutral-100">
                  <td className="px-5 py-2.5 font-mono text-caption text-neutral-800">
                    {rate.sku}
                  </td>
                  <td className="px-5 py-2.5">
                    <ProviderBadge provider={rate.provider} />
                  </td>
                  <td className="px-5 py-2.5 text-right font-mono tabular-nums text-neutral-800">
                    {formatRate(rate.amount, rate.unit)}
                  </td>
                  <td className="px-5 py-2.5 font-mono text-caption text-neutral-500">
                    {rate.region}
                  </td>
                  <td className="px-5 py-2.5">
                    <span
                      className={
                        rate.api_verified
                          ? "inline-flex items-center gap-1 rounded-full bg-status-success/10 px-2 py-0.5 text-caption font-medium text-status-success"
                          : "inline-flex items-center gap-1 rounded-full bg-status-warning/10 px-2 py-0.5 text-caption font-medium text-[#92400E]"
                      }
                      title={meta.detail}
                    >
                      {rate.api_verified && <ShieldCheck size={11} aria-hidden />}
                      {meta.label}
                    </span>
                  </td>
                  <td className="px-5 py-2.5 text-caption text-neutral-400">
                    {rate.meter || "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
