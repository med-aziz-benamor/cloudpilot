import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { ForecastResponse } from "@/types";

export function useForecast(horizonDays: 30 | 60 | 90 = 30) {
  return useQuery({
    queryKey: ["forecast", horizonDays],
    retry: false,
    queryFn: async () =>
      (
        await api.get<ForecastResponse>(
          `/api/v1/forecast?horizon_days=${horizonDays}`,
        )
      ).data,
  });
}

export function useSetBudget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (budgetUsd: number) =>
      (
        await api.patch<{ budget_usd: number | null }>(
          "/api/v1/forecast/budget",
          { budget_usd: budgetUsd },
        )
      ).data,
    // The budget is what over_budget/overrun_pct are computed against, and it
    // also gates ForecastAgent's alerts — so refresh the forecast (every
    // horizon) and the recommendations that quote it.
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["forecast"] });
      qc.invalidateQueries({ queryKey: ["recommendations"] });
    },
  });
}
