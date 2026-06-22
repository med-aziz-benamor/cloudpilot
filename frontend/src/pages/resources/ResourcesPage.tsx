import { ChevronDown, ChevronRight, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/domain/EmptyState";
import { ProviderBadge } from "@/components/domain/ProviderBadge";
import { ResourceTreeRow } from "@/components/domain/ResourceTreeRow";
import { SparklineChart } from "@/components/domain/SparklineChart";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useResourceDetail, useResources } from "@/hooks/useResources";
import { PageHeader } from "@/components/layout/PageHeader";
import { cn, formatCurrency } from "@/lib/utils";
import type { CloudProvider } from "@/types";

export function ResourcesPage() {
  const [selectedProvider, setSelectedProvider] = useState<CloudProvider | null>(null);
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set(["azure"]));

  const { data: resources, isLoading } = useResources();
  const detail = useResourceDetail(selectedId);

  // Build provider → region map for the left tree.
  const tree = useMemo(() => {
    const map: Record<string, Set<string>> = {};
    (resources ?? []).forEach((r) => {
      map[r.provider] ??= new Set();
      map[r.provider].add(r.region);
    });
    return map;
  }, [resources]);

  const filtered = (resources ?? []).filter((r) => {
    if (selectedProvider && r.provider !== selectedProvider) return false;
    if (selectedRegion && r.region !== selectedRegion) return false;
    if (search && !r.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div>
      <PageHeader
        title="Resources"
        description="Explore your multi-cloud inventory across providers, regions and services."
      />

      <div className="grid grid-cols-12 gap-4">
        {/* Left: provider tree */}
        <Card className="col-span-12 p-2 md:col-span-3 lg:col-span-2">
          <button
            onClick={() => {
              setSelectedProvider(null);
              setSelectedRegion(null);
            }}
            className={cn(
              "mb-1 w-full rounded-md px-3 py-2 text-left text-body-sm font-medium",
              !selectedProvider ? "bg-brand-primary/[0.07] text-brand-primary" : "hover:bg-neutral-50",
            )}
          >
            All providers
          </button>
          {Object.entries(tree).map(([provider, regions]) => (
            <div key={provider}>
              <button
                onClick={() => {
                  setExpanded((prev) => {
                    const next = new Set(prev);
                    next.has(provider) ? next.delete(provider) : next.add(provider);
                    return next;
                  });
                  setSelectedProvider(provider as CloudProvider);
                  setSelectedRegion(null);
                }}
                className="flex w-full items-center gap-1 rounded-md px-2 py-2 text-left hover:bg-neutral-50"
              >
                {expanded.has(provider) ? (
                  <ChevronDown size={14} className="text-neutral-400" />
                ) : (
                  <ChevronRight size={14} className="text-neutral-400" />
                )}
                <ProviderBadge provider={provider as CloudProvider} size="sm" />
              </button>
              {expanded.has(provider) &&
                [...regions].map((region) => (
                  <button
                    key={region}
                    onClick={() => {
                      setSelectedProvider(provider as CloudProvider);
                      setSelectedRegion(region);
                    }}
                    className={cn(
                      "ml-6 block rounded-md px-2 py-1 text-left text-body-sm",
                      selectedRegion === region
                        ? "text-brand-primary"
                        : "text-neutral-500 hover:text-neutral-900",
                    )}
                  >
                    {region}
                  </button>
                ))}
            </div>
          ))}
        </Card>

        {/* Middle: resource list */}
        <Card className="col-span-12 p-2 md:col-span-5 lg:col-span-4">
          <div className="relative p-2">
            <Search size={15} className="absolute left-4 top-1/2 -translate-y-1/2 text-neutral-400" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search resources…"
              className="pl-9"
            />
          </div>
          <div className="max-h-[70vh] overflow-y-auto">
            {isLoading ? (
              Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="m-2 h-14" />
              ))
            ) : filtered.length === 0 ? (
              <EmptyState title="No resources" description="Adjust filters or seed demo data." className="m-2" />
            ) : (
              filtered.map((r) => (
                <ResourceTreeRow
                  key={r.id}
                  resource={r}
                  selected={selectedId === r.id}
                  onClick={() => setSelectedId(r.id)}
                />
              ))
            )}
          </div>
        </Card>

        {/* Right: detail */}
        <div className="col-span-12 md:col-span-4 lg:col-span-6">
          {!selectedId ? (
            <EmptyState
              title="Select a resource"
              description="Choose a resource from the list to inspect metrics, cost and recommendations."
            />
          ) : detail.isLoading || !detail.data ? (
            <div className="space-y-4">
              <Skeleton className="h-24" />
              <Skeleton className="h-48" />
            </div>
          ) : (
            <div className="space-y-4">
              <Card className="p-5">
                <div className="flex items-center justify-between">
                  <h2 className="font-mono text-h3 font-semibold text-neutral-900">
                    {detail.data.name}
                  </h2>
                  <ProviderBadge provider={detail.data.provider} />
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-caption text-neutral-500">
                  <span className="rounded-full bg-neutral-100 px-2 py-0.5">
                    {detail.data.region}
                  </span>
                  <span className="rounded-full bg-neutral-100 px-2 py-0.5">
                    {detail.data.service.replace(/_/g, " ")}
                  </span>
                  {detail.data.sku && (
                    <span className="rounded-full bg-neutral-100 px-2 py-0.5 font-mono">
                      {detail.data.sku}
                    </span>
                  )}
                </div>
              </Card>

              <div className="grid grid-cols-2 gap-3">
                {detail.data.metrics.map((m) => {
                  const avg =
                    m.points.reduce((s, p) => s + p.value, 0) /
                    (m.points.length || 1);
                  return (
                    <Card key={m.metric_name} className="p-4">
                      <p className="text-label uppercase text-neutral-400">
                        {m.metric_name.replace(/_/g, " ")}
                      </p>
                      <p className="mt-1 text-h2 font-bold tabular-nums">
                        {avg.toFixed(0)}
                        <span className="text-body text-neutral-400">%</span>
                      </p>
                      <SparklineChart
                        data={m.points.slice(-48).map((p) => p.value)}
                        height={36}
                      />
                    </Card>
                  );
                })}
              </div>

              <Card className="p-5">
                <h3 className="mb-2 text-h4 font-semibold">30-day cost trend</h3>
                <SparklineChart
                  data={detail.data.cost_trend.map((p) => p.value)}
                  height={120}
                  color="#0D6EFD"
                />
                <p className="mt-2 text-body-sm text-neutral-500">
                  Monthly cost:{" "}
                  <span className="font-semibold text-neutral-900">
                    {formatCurrency(detail.data.monthly_cost_usd)}
                  </span>{" "}
                  · {detail.data.recommendation_count} active recommendation(s)
                </p>
              </Card>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
