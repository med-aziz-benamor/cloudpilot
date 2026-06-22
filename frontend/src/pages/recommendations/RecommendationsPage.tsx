import { AnimatePresence } from "framer-motion";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { EmptyState } from "@/components/domain/EmptyState";
import { RecommendationCard } from "@/components/domain/RecommendationCard";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useRecommendations,
  useSavingsSummary,
  useUpdateRecommendation,
} from "@/hooks/useRecommendations";
import { AGENT_META } from "@/lib/constants";
import { cn, formatCurrency } from "@/lib/utils";
import { useUIStore } from "@/stores/ui.store";
import type { AgentType, RecommendationStatus } from "@/types";

const AGENTS: (AgentType | "all")[] = ["all", "cost", "rightsizing", "forecast", "architect"];
const STATUSES: (RecommendationStatus | "all")[] = [
  "all",
  "pending",
  "accepted",
  "rejected",
  "snoozed",
];

export function RecommendationsPage() {
  const navigate = useNavigate();
  const addToast = useUIStore((s) => s.addToast);
  const [agent, setAgent] = useState<AgentType | "all">("all");
  const [status, setStatus] = useState<RecommendationStatus | "all">("all");
  const [sort, setSort] = useState("impact");

  const { data, isLoading } = useRecommendations({
    agent: agent === "all" ? undefined : agent,
    status: status === "all" ? undefined : status,
    sort,
  });
  const savings = useSavingsSummary();
  const update = useUpdateRecommendation();

  const act = (id: string, newStatus: RecommendationStatus, snooze?: number) => {
    update.mutate(
      { id, update: { status: newStatus, snooze_hours: snooze } },
      {
        onSuccess: () =>
          addToast({
            type: newStatus === "accepted" ? "success" : "info",
            title: `Recommendation ${newStatus}`,
          }),
        onError: () => addToast({ type: "error", title: "Update failed" }),
      },
    );
  };

  return (
    <div>
      <PageHeader
        title="Recommendations"
        description="Actionable, AI-generated optimizations across your cloud estate."
      />

      {/* Savings banner */}
      <Card className="mb-6 flex items-center justify-between bg-gradient-to-r from-brand-primary to-brand-accent p-5 text-white">
        <div>
          <p className="text-body-sm text-white/80">
            💰 Total estimated savings if all accepted
          </p>
          <p className="text-display font-extrabold tabular-nums">
            {formatCurrency(savings.data?.total_potential_usd ?? 0)}
            <span className="text-h3 font-medium text-white/70">/month</span>
          </p>
        </div>
        <div className="hidden text-right text-body-sm text-white/80 sm:block">
          <p>{savings.data?.pending_count ?? 0} pending</p>
          <p>{savings.data?.accepted_count ?? 0} accepted</p>
        </div>
      </Card>

      <div className="grid grid-cols-12 gap-6">
        {/* Filters */}
        <div className="col-span-12 space-y-4 lg:col-span-3">
          <Card className="p-4">
            <p className="mb-2 text-label uppercase text-neutral-400">Agent</p>
            <div className="space-y-1">
              {AGENTS.map((a) => (
                <button
                  key={a}
                  onClick={() => setAgent(a)}
                  className={cn(
                    "block w-full rounded-md px-2 py-1.5 text-left text-body-sm capitalize",
                    agent === a ? "bg-brand-primary/[0.07] text-brand-primary" : "hover:bg-neutral-50",
                  )}
                >
                  {a === "all" ? "All agents" : AGENT_META[a as AgentType].label}
                </button>
              ))}
            </div>
          </Card>

          <Card className="p-4">
            <p className="mb-2 text-label uppercase text-neutral-400">Status</p>
            <div className="space-y-1">
              {STATUSES.map((s) => (
                <button
                  key={s}
                  onClick={() => setStatus(s)}
                  className={cn(
                    "block w-full rounded-md px-2 py-1.5 text-left text-body-sm capitalize",
                    status === s ? "bg-brand-primary/[0.07] text-brand-primary" : "hover:bg-neutral-50",
                  )}
                >
                  {s}
                </button>
              ))}
            </div>
          </Card>

          <Card className="p-4">
            <p className="mb-2 text-label uppercase text-neutral-400">Sort by</p>
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value)}
              className="w-full rounded-md border border-neutral-200 px-2 py-1.5 text-body-sm"
            >
              <option value="impact">Impact</option>
              <option value="confidence">Confidence</option>
              <option value="date">Date</option>
            </select>
          </Card>
        </div>

        {/* Feed */}
        <div className="col-span-12 space-y-3 lg:col-span-9">
          {isLoading ? (
            Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-40" />)
          ) : data?.length === 0 ? (
            <EmptyState
              title="No recommendations"
              description="No matches for the current filters. The agents run continuously."
            />
          ) : (
            <AnimatePresence mode="popLayout">
              {data?.map((r) => (
                <RecommendationCard
                  key={r.id}
                  recommendation={r}
                  onAccept={() => act(r.id, "accepted")}
                  onReject={() => act(r.id, "rejected")}
                  onSnooze={() => act(r.id, "snoozed", 24)}
                  onInvestigate={() => navigate("/resources")}
                />
              ))}
            </AnimatePresence>
          )}
        </div>
      </div>
    </div>
  );
}
