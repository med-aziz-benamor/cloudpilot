import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Resource, ResourceDetail, ResourceTreeNode } from "@/types";

export function useResources(filters?: {
  provider?: string;
  service?: string;
  region?: string;
}) {
  const params = new URLSearchParams();
  if (filters?.provider) params.set("provider", filters.provider);
  if (filters?.service) params.set("service", filters.service);
  if (filters?.region) params.set("region", filters.region);
  const qs = params.toString();
  return useQuery({
    queryKey: ["resources", filters],
    queryFn: async () =>
      (await api.get<Resource[]>(`/api/v1/resources${qs ? `?${qs}` : ""}`)).data,
  });
}

export function useResourceTree() {
  return useQuery({
    queryKey: ["resource-tree"],
    queryFn: async () =>
      (await api.get<ResourceTreeNode[]>("/api/v1/resources/tree")).data,
  });
}

export function useResourceDetail(resourceId: string | null) {
  return useQuery({
    queryKey: ["resource-detail", resourceId],
    enabled: !!resourceId,
    queryFn: async () =>
      (await api.get<ResourceDetail>(`/api/v1/resources/${resourceId}`)).data,
  });
}
