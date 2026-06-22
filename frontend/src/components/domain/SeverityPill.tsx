import { Badge } from "@/components/ui/badge";
import type { RecommendationStatus } from "@/types";

const STATUS_VARIANT: Record<
  RecommendationStatus,
  "warning" | "success" | "danger" | "default"
> = {
  pending: "warning",
  accepted: "success",
  rejected: "danger",
  snoozed: "default",
};

const STATUS_LABEL: Record<RecommendationStatus, string> = {
  pending: "Pending",
  accepted: "Accepted",
  rejected: "Rejected",
  snoozed: "Snoozed",
};

export function StatusBadge({ status }: { status: RecommendationStatus }) {
  return <Badge variant={STATUS_VARIANT[status]}>{STATUS_LABEL[status]}</Badge>;
}

/** Confidence as a colored pill (high=green, med=amber, low=neutral). */
export function ConfidencePill({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const variant = pct >= 85 ? "success" : pct >= 70 ? "info" : "default";
  return <Badge variant={variant}>{pct}% confidence</Badge>;
}

export function SeverityPill({
  level,
  label,
}: {
  level: "success" | "warning" | "danger" | "info";
  label: string;
}) {
  return <Badge variant={level}>{label}</Badge>;
}
