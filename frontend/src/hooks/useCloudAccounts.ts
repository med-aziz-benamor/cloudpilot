import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { CloudAccount, CloudProvider } from "@/types";

interface ConnectPayload {
  provider: CloudProvider;
  display_name: string;
  account_identifier: string;
  credentials: Record<string, unknown>;
}

export function useCloudAccounts() {
  return useQuery({
    queryKey: ["cloud-accounts"],
    queryFn: async () =>
      (await api.get<CloudAccount[]>("/api/v1/cloud-accounts")).data,
  });
}

export function useTestConnection() {
  return useMutation({
    mutationFn: async (payload: ConnectPayload) =>
      (
        await api.post<{
          valid: boolean;
          message: string;
          resource_count: number | null;
        }>("/api/v1/cloud-accounts/test", payload)
      ).data,
  });
}

export function useConnectAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: ConnectPayload) =>
      (await api.post<CloudAccount>("/api/v1/cloud-accounts", payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cloud-accounts"] }),
  });
}

export function useDeleteAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) =>
      (await api.delete(`/api/v1/cloud-accounts/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cloud-accounts"] }),
  });
}
