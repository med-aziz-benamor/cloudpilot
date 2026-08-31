import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { PricingCatalog } from "@/types";

/**
 * The rate card every quoted saving is derived from.
 *
 * It is a pinned snapshot refreshed by an operator, not live data, so it is cached
 * for the session rather than refetched on focus.
 */
export function usePricingCatalog() {
  return useQuery({
    queryKey: ["pricing-catalog"],
    queryFn: async () =>
      (await api.get<PricingCatalog>("/api/v1/pricing/catalog")).data,
    staleTime: Infinity,
  });
}
