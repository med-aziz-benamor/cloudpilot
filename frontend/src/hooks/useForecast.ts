import { useQuery } from "@tanstack/react-query";

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
