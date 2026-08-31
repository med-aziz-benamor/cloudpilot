import { ShieldCheck, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ProviderBadge } from "@/components/domain/ProviderBadge";
import { RateCardPanel } from "@/components/domain/RateCardPanel";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCloudAccounts, useDeleteAccount } from "@/hooks/useCloudAccounts";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth.store";

interface AuditEntry {
  id: string;
  event_type: string;
  resource_type: string | null;
  ip_address: string | null;
  created_at: string;
}

export function SettingsPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const accounts = useCloudAccounts();
  const deleteAccount = useDeleteAccount();
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const pendingAccount = accounts.data?.find((a) => a.id === pendingDeleteId);

  const audit = useQuery({
    queryKey: ["audit-log"],
    queryFn: async () =>
      (await api.get<AuditEntry[]>("/api/v1/admin/audit-log?limit=50")).data,
    retry: false,
  });

  return (
    <div>
      <PageHeader title="Settings" description="Manage accounts, users and security." />

      <Tabs defaultValue="accounts">
        <TabsList>
          <TabsTrigger value="accounts">Cloud Accounts</TabsTrigger>
          <TabsTrigger value="pricing">Pricing</TabsTrigger>
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="audit">Audit Log</TabsTrigger>
        </TabsList>

        <TabsContent value="accounts">
          <div className="mb-4 flex justify-end">
            <Button onClick={() => navigate("/settings/connect")}>
              + Connect cloud account
            </Button>
          </div>
          <div className="space-y-3">
            {(accounts.data ?? []).map((a) => (
              <Card key={a.id} className="flex items-center gap-4 p-4">
                <ProviderBadge provider={a.provider} />
                <div className="flex-1">
                  <p className="text-body-sm font-medium text-neutral-900">
                    {a.display_name}
                  </p>
                  <p className="font-mono text-caption text-neutral-400">
                    {a.account_identifier} · synced {timeAgo(a.last_synced_at)}
                  </p>
                </div>
                <Badge variant={a.status === "active" ? "success" : "warning"}>
                  {a.status}
                </Badge>
                <Button
                  variant="ghost"
                  size="icon"
                  className="text-neutral-400 hover:text-status-danger"
                  onClick={() => setPendingDeleteId(a.id)}
                  disabled={deleteAccount.isPending}
                  aria-label="Disconnect"
                >
                  <Trash2 size={16} />
                </Button>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="pricing">
          <RateCardPanel />
        </TabsContent>

        <TabsContent value="profile">
          <Card className="max-w-lg p-6">
            <h3 className="mb-4 text-h4 font-semibold">Your profile</h3>
            <dl className="space-y-3 text-body-sm">
              <div className="flex justify-between">
                <dt className="text-neutral-500">Name</dt>
                <dd className="font-medium">{user?.full_name}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-neutral-500">Email</dt>
                <dd className="font-medium">{user?.email}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-neutral-500">Role</dt>
                <dd>
                  <Badge variant="brand" className="capitalize">
                    {user?.role}
                  </Badge>
                </dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-neutral-500">Two-factor auth</dt>
                <dd className="flex items-center gap-1 text-neutral-400">
                  <ShieldCheck size={15} /> {user?.mfa_enabled ? "Enabled" : "Disabled"}
                </dd>
              </div>
            </dl>
          </Card>
        </TabsContent>

        <TabsContent value="audit">
          <Card className="overflow-hidden">
            <table className="w-full text-body-sm">
              <thead className="border-b border-neutral-200 bg-neutral-50 text-left text-caption uppercase text-neutral-400">
                <tr>
                  <th className="px-5 py-3">Event</th>
                  <th className="px-5 py-3">Resource</th>
                  <th className="px-5 py-3">IP</th>
                  <th className="px-5 py-3 text-right">When</th>
                </tr>
              </thead>
              <tbody>
                {(audit.data ?? []).map((e) => (
                  <tr key={e.id} className="border-b border-neutral-100">
                    <td className="px-5 py-2.5 font-mono text-caption text-neutral-700">
                      {e.event_type}
                    </td>
                    <td className="px-5 py-2.5 text-neutral-500">
                      {e.resource_type ?? "—"}
                    </td>
                    <td className="px-5 py-2.5 font-mono text-caption text-neutral-400">
                      {e.ip_address ?? "—"}
                    </td>
                    <td className="px-5 py-2.5 text-right text-neutral-400">
                      {timeAgo(e.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {audit.isError && (
              <p className="p-5 text-center text-body-sm text-neutral-400">
                Audit log requires admin access.
              </p>
            )}
          </Card>
        </TabsContent>
      </Tabs>

      <ConfirmDialog
        open={pendingDeleteId !== null}
        onOpenChange={(open) => !open && setPendingDeleteId(null)}
        title="Disconnect cloud account"
        description={
          pendingAccount
            ? `This disconnects "${pendingAccount.display_name}". CloudPilot will stop syncing its resources and billing.`
            : "This disconnects the cloud account."
        }
        confirmLabel="Disconnect"
        isPending={deleteAccount.isPending}
        onConfirm={() => {
          if (!pendingDeleteId) return;
          deleteAccount.mutate(pendingDeleteId, {
            onSuccess: () => setPendingDeleteId(null),
          });
        }}
      />
    </div>
  );
}
