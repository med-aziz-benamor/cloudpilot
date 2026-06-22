import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  AnomalyEntry,
  CostBreakdown,
  CostSummary,
  CostTimeseriesPoint,
  TopCostDriver,
} from "@/types";

export function useCostSummary() {
  return useQuery({
    queryKey: ["cost-summary"],
    queryFn: async () => (await api.get<CostSummary>("/api/v1/costs/summary")).data,
  });
}

export function useCostTimeseries(periodDays: number) {
  return useQuery({
    queryKey: ["cost-timeseries", periodDays],
    queryFn: async () =>
      (
        await api.get<{ period_days: number; points: CostTimeseriesPoint[] }>(
          `/api/v1/costs/timeseries?period_days=${periodDays}`,
        )
      ).data.points,
  });
}

export function useCostBreakdown() {
  return useQuery({
    queryKey: ["cost-breakdown"],
    queryFn: async () =>
      (await api.get<CostBreakdown>("/api/v1/costs/breakdown")).data,
  });
}

export function useTopDrivers(limit = 5) {
  return useQuery({
    queryKey: ["top-drivers", limit],
    queryFn: async () =>
      (await api.get<TopCostDriver[]>(`/api/v1/costs/top-drivers?limit=${limit}`))
        .data,
  });
}

export function useAnomalies() {
  return useQuery({
    queryKey: ["anomalies"],
    queryFn: async () =>
      (await api.get<AnomalyEntry[]>("/api/v1/costs/anomalies")).data,
  });
}
