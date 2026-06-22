import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Recommendation, SavingsSummary } from "@/types";
import type { RecommendationStatusUpdate } from "@/types/api";

export function useRecommendations(filters?: {
  agent?: string;
  status?: string;
  sort?: string;
}) {
  const params = new URLSearchParams();
  if (filters?.agent) params.set("agent", filters.agent);
  if (filters?.status) params.set("status", filters.status);
  if (filters?.sort) params.set("sort", filters.sort);
  const qs = params.toString();
  return useQuery({
    queryKey: ["recommendations", filters],
    queryFn: async () =>
      (
        await api.get<Recommendation[]>(
          `/api/v1/recommendations${qs ? `?${qs}` : ""}`,
        )
      ).data,
  });
}

export function useSavingsSummary() {
  return useQuery({
    queryKey: ["savings-summary"],
    queryFn: async () =>
      (await api.get<SavingsSummary>("/api/v1/recommendations/savings")).data,
  });
}

export function useUpdateRecommendation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      update,
    }: {
      id: string;
      update: RecommendationStatusUpdate;
    }) =>
      (
        await api.patch<Recommendation>(
          `/api/v1/recommendations/${id}/status`,
          update,
        )
      ).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["recommendations"] });
      qc.invalidateQueries({ queryKey: ["savings-summary"] });
      qc.invalidateQueries({ queryKey: ["cost-summary"] });
    },
  });
}
