import { motion } from "framer-motion";
import { Check, Loader2, Lock } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useConnectAccount, useTestConnection } from "@/hooks/useCloudAccounts";
import { PROVIDER_META } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/stores/ui.store";
import type { CloudProvider } from "@/types";

const STEPS = ["Provider", "Credentials", "Test", "Done"];

const FIELDS: Record<CloudProvider, { key: string; label: string; secret?: boolean }[]> = {
  azure: [
    { key: "tenant_id", label: "Tenant ID" },
    { key: "client_id", label: "Client ID" },
    { key: "client_secret", label: "Client Secret", secret: true },
    { key: "subscription_id", label: "Subscription ID" },
  ],
  aws: [
    { key: "account_id", label: "Account ID" },
    { key: "role_arn", label: "IAM Role ARN" },
    { key: "external_id", label: "External ID" },
  ],
  gcp: [
    { key: "project_id", label: "Project ID" },
    { key: "service_account_json", label: "Service Account JSON", secret: true },
  ],
};

export function ConnectCloudPage() {
  const navigate = useNavigate();
  const addToast = useUIStore((s) => s.addToast);
  const test = useTestConnection();
  const connect = useConnectAccount();

  const [step, setStep] = useState(0);
  const [provider, setProvider] = useState<CloudProvider | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [creds, setCreds] = useState<Record<string, string>>({});
  const [resourceCount, setResourceCount] = useState<number | null>(null);

  const identifierKey = provider === "azure" ? "subscription_id" : provider === "aws" ? "account_id" : "project_id";

  const runTest = async () => {
    if (!provider) return;
    setStep(2);
    const result = await test.mutateAsync({
      provider,
      display_name: displayName || `${PROVIDER_META[provider].label} account`,
      account_identifier: creds[identifierKey] || "demo",
      credentials: creds,
    });
    if (result.valid) {
      setResourceCount(result.resource_count ?? 0);
    } else {
      addToast({ type: "error", title: "Connection failed", description: result.message });
      setStep(1);
    }
  };

  const finish = async () => {
    if (!provider) return;
    await connect.mutateAsync({
      provider,
      display_name: displayName || `${PROVIDER_META[provider].label} account`,
      account_identifier: creds[identifierKey] || "demo",
      credentials: creds,
    });
    setStep(3);
    setTimeout(() => navigate("/"), 2500);
  };

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Connect a cloud account" description="Read-only access only — CloudPilot never modifies your resources." />

      {/* Stepper */}
      <div className="mb-8 flex items-center justify-between">
        {STEPS.map((label, i) => (
          <div key={label} className="flex flex-1 items-center">
            <div
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-full text-body-sm font-semibold",
                i < step
                  ? "bg-status-success text-white"
                  : i === step
                    ? "bg-brand-primary text-white"
                    : "bg-neutral-100 text-neutral-400",
              )}
            >
              {i < step ? <Check size={16} /> : i + 1}
            </div>
            <span className={cn("ml-2 text-body-sm", i === step ? "font-medium text-neutral-900" : "text-neutral-400")}>
              {label}
            </span>
            {i < STEPS.length - 1 && <div className="mx-2 h-px flex-1 bg-neutral-200" />}
          </div>
        ))}
      </div>

      {/* Step 1: provider */}
      {step === 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {(["azure", "aws", "gcp"] as const).map((p) => (
            <button
              key={p}
              onClick={() => setProvider(p)}
              className={cn(
                "rounded-card border-2 bg-white p-5 text-left transition-all hover:shadow-card-hover",
                provider === p ? "border-brand-primary shadow-glow-brand" : "border-neutral-200",
              )}
            >
              <div
                className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-lg text-white"
                style={{ backgroundColor: PROVIDER_META[p].color }}
              >
                {PROVIDER_META[p].label[0]}
              </div>
              <p className="font-semibold text-neutral-900">{PROVIDER_META[p].label}</p>
              <p className="text-caption text-neutral-400">
                Connect via read-only credentials
              </p>
              {provider === p && <Check size={18} className="mt-2 text-brand-primary" />}
            </button>
          ))}
          <div className="sm:col-span-3">
            <Button className="w-full" disabled={!provider} onClick={() => setStep(1)}>
              Continue
            </Button>
          </div>
        </div>
      )}

      {/* Step 2: credentials */}
      {step === 1 && provider && (
        <Card className="p-6">
          <Input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder={`${PROVIDER_META[provider].label} account name`}
            className="mb-4"
          />
          <div className="space-y-3">
            {FIELDS[provider].map((f) => (
              <div key={f.key}>
                <label className="mb-1 block text-body-sm font-medium text-neutral-700">
                  {f.label}
                </label>
                <div className="relative">
                  <Lock size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
                  <Input
                    type={f.secret ? "password" : "text"}
                    value={creds[f.key] ?? ""}
                    onChange={(e) => setCreds((c) => ({ ...c, [f.key]: e.target.value }))}
                    className="pl-9"
                  />
                </div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-caption text-neutral-400">
            🔒 Encrypted at rest with AES-256 (Fernet). Demo mode accepts any values.
          </p>
          <div className="mt-5 flex gap-2">
            <Button variant="outline" onClick={() => setStep(0)}>
              Back
            </Button>
            <Button className="flex-1" onClick={runTest}>
              Test connection
            </Button>
          </div>
        </Card>
      )}

      {/* Step 3: testing */}
      {step === 2 && (
        <Card className="p-8">
          <div className="space-y-3">
            {[
              "Validating credentials format",
              `Connecting to ${provider ? PROVIDER_META[provider].label : ""} API`,
              "Verifying read-only permissions",
              resourceCount !== null ? `Found ${resourceCount} resources` : "Discovering resources",
            ].map((label, i) => {
              const done = test.isSuccess && (resourceCount !== null || i < 3);
              return (
                <div key={label} className="flex items-center gap-3 text-body-sm">
                  {done ? (
                    <Check size={16} className="text-status-success" />
                  ) : (
                    <Loader2 size={16} className="animate-spin text-brand-primary" />
                  )}
                  <span className={done ? "text-neutral-900" : "text-neutral-400"}>
                    {label}
                  </span>
                </div>
              );
            })}
          </div>
          {resourceCount !== null && (
            <Button className="mt-6 w-full" onClick={finish} disabled={connect.isPending}>
              {connect.isPending ? <Loader2 className="animate-spin" size={16} /> : "Confirm & connect"}
            </Button>
          )}
        </Card>
      )}

      {/* Step 4: success */}
      {step === 3 && provider && (
        <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}>
          <Card className="p-10 text-center">
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: "spring", stiffness: 200 }}
              className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-status-success/10"
            >
              <Check size={32} className="text-status-success" />
            </motion.div>
            <h2 className="text-h2 font-bold text-neutral-900">
              {PROVIDER_META[provider].label} connected!
            </h2>
            <p className="mt-2 text-body text-neutral-500">
              Syncing {resourceCount} resources · redirecting to dashboard…
            </p>
          </Card>
        </motion.div>
      )}
    </div>
  );
}
