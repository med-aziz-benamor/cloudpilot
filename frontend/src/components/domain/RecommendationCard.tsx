import { motion } from "framer-motion";
import { Check, Clock, ExternalLink, X } from "lucide-react";
import { forwardRef } from "react";

import { AgentBadge } from "@/components/domain/AgentBadge";
import { CalculationBasis } from "@/components/domain/CalculationBasis";
import { ConfidencePill, StatusBadge } from "@/components/domain/SeverityPill";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { AGENT_META } from "@/lib/constants";
import { cn, formatCurrency } from "@/lib/utils";
import type { Recommendation } from "@/types";

interface RecommendationCardProps {
  recommendation: Recommendation;
  onAccept?: () => void;
  onReject?: () => void;
  onSnooze?: () => void;
  onInvestigate?: () => void;
}

/**
 * Rich recommendation card with agent color accent and animated actions.
 *
 * `forwardRef` is required, not stylistic: the feed wraps these in an
 * `AnimatePresence mode="popLayout"`, which measures each exiting child so the
 * remaining cards can slide up smoothly. Measuring needs a ref on the child, and
 * a plain function component silently drops it — React warns, and the exit
 * animation degrades.
 */
export const RecommendationCard = forwardRef<HTMLDivElement, RecommendationCardProps>(
  function RecommendationCard(
    { recommendation: r, onAccept, onReject, onSnooze, onInvestigate },
    ref,
  ) {
  const accent = AGENT_META[r.agent].color;
  const isPending = r.status === "pending";

  return (
    <motion.div
      ref={ref}
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -40 }}
      transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
    >
      <Card
        className="overflow-hidden p-5 transition-shadow hover:shadow-card-hover"
        style={{ borderLeft: `3px solid ${accent}` }}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AgentBadge agent={r.agent} />
            <ConfidencePill value={r.confidence} />
          </div>
          <StatusBadge status={r.status} />
        </div>

        <h3 className="mt-3 text-h4 font-semibold text-neutral-900">{r.title}</h3>
        <p className="mt-1 line-clamp-2 text-body-sm text-neutral-500">
          {r.description}
        </p>

        {r.affected_resource_names.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {r.affected_resource_names.map((name) => (
              <span
                key={name}
                className="rounded-full bg-neutral-100 px-2 py-0.5 font-mono text-caption text-neutral-600"
              >
                {name}
              </span>
            ))}
          </div>
        )}

        <div className="mt-4 flex items-center justify-between">
          {r.estimated_saving_usd ? (
            <p className="text-body-sm font-semibold text-status-success">
              Save {formatCurrency(r.estimated_saving_usd)}/month
            </p>
          ) : (
            <p className="text-body-sm font-medium text-status-warning">
              Budget alert
            </p>
          )}

          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" onClick={onInvestigate}>
              Investigate <ExternalLink size={14} />
            </Button>
            {isPending && (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onAccept}
                  className="text-status-success hover:bg-status-success/10"
                >
                  <Check size={15} /> Accept
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onReject}
                  className="text-status-danger hover:bg-status-danger/10"
                >
                  <X size={15} /> Reject
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={onSnooze}
                  className={cn("text-neutral-400 hover:text-neutral-700")}
                  aria-label="Snooze"
                >
                  <Clock size={15} />
                </Button>
              </>
            )}
          </div>
        </div>

        <CalculationBasis recommendation={r} />
      </Card>
    </motion.div>
  );
});
