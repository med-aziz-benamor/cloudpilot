// Reading the calculation basis a recommendation carries in its `metadata`.
//
// `metadata` is JSONB written by whichever agent produced the recommendation, so
// it is genuinely `unknown` at the type level: rows created before a field existed
// will not have it, and an agent that could not price a SKU stores `null` rather
// than a fabricated rate. Everything here narrows defensively and returns null
// rather than rendering a partial basis, because a half-shown derivation is worse
// than none — it looks like the whole answer.

import type {
  PriceSource,
  PriceUnit,
  PricingProvenance,
  Recommendation,
} from "@/types";

/** How defensible a rate is, and what to call it on screen. */
export const PRICE_SOURCE_META: Record<
  PriceSource,
  { label: string; verified: boolean; detail: string }
> = {
  azure_retail_api: {
    label: "Azure Retail API",
    verified: true,
    detail: "Fetched from Microsoft's public rate-card API.",
  },
  aws_price_list: {
    label: "AWS Price List",
    verified: true,
    detail: "Fetched from the AWS Price List offer file.",
  },
  published_list_price: {
    label: "Published list price",
    verified: false,
    detail:
      "Transcribed from the provider's public pricing page — real, but not machine-verified.",
  },
};

/** The rightsizing agent's basis: two rates, a node count, and where each rate came from. */
export interface RightsizingBasis {
  kind: "rightsizing";
  currentSku: string;
  targetSku: string;
  nodeCount: number;
  currentRate: number;
  targetRate: number;
  hoursPerMonth: number;
  p95Cpu: number | null;
  p95Mem: number | null;
  pricing: { current: PricingProvenance | null; target: PricingProvenance | null };
}

/** The cost agent's basis: what it expected to be billed against what was. */
export interface AnomalyBasis {
  kind: "anomaly";
  service: string;
  anomalyDate: string;
  expected: number;
  actual: number;
  delta: number;
  zScore: number;
}

/** The forecast agent's basis: spend so far, projected, against the budget. */
export interface BudgetBasis {
  kind: "budget";
  mtd: number;
  projected: number;
  budget: number;
  overrunPct: number;
}

export type CalculationBasis = RightsizingBasis | AnomalyBasis | BudgetBasis;

// ─── narrowing helpers ───
type Meta = Record<string, unknown>;

function num(meta: Meta, key: string): number | null {
  const v = meta[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function str(meta: Meta, key: string): string | null {
  const v = meta[key];
  return typeof v === "string" && v.length > 0 ? v : null;
}

const UNITS: PriceUnit[] = ["hour", "gb_month"];

/** Narrow one `pricing_provenance()` record, or null if it is absent or malformed. */
function readProvenance(value: unknown): PricingProvenance | null {
  if (typeof value !== "object" || value === null) return null;
  const p = value as Meta;
  const rate = num(p, "rate");
  const unit = str(p, "unit");
  const source = str(p, "source");
  const region = str(p, "region");
  const asOf = str(p, "as_of");
  if (rate === null || !unit || !source || !region || !asOf) return null;
  if (!UNITS.includes(unit as PriceUnit)) return null;
  if (!(source in PRICE_SOURCE_META)) return null;
  return {
    rate,
    unit: unit as PriceUnit,
    currency: str(p, "currency") ?? "USD",
    region,
    source: source as PriceSource,
    meter: str(p, "meter") ?? "",
    as_of: asOf,
  };
}

/**
 * Read the basis a recommendation was derived from, or null if its metadata does
 * not carry one.
 *
 * Keyed on the agent rather than on shape: two agents could plausibly both store a
 * `service` field, and guessing from keys would eventually render one agent's
 * numbers under another's labels.
 */
export function readBasis(r: Recommendation): CalculationBasis | null {
  const meta = (r.metadata ?? {}) as Meta;

  if (r.agent === "rightsizing") {
    const currentSku = str(meta, "current_sku");
    const targetSku = str(meta, "target_sku");
    const currentRate = num(meta, "current_price_usd_hr");
    const targetRate = num(meta, "target_price_usd_hr");
    if (!currentSku || !targetSku || currentRate === null || targetRate === null) {
      return null;
    }
    const pricing = (meta.pricing ?? {}) as Meta;
    return {
      kind: "rightsizing",
      currentSku,
      targetSku,
      nodeCount: num(meta, "node_count") ?? 1,
      currentRate,
      targetRate,
      // 730 is the FinOps convention, and the agent stores what it actually used.
      hoursPerMonth: num(meta, "billable_hours_per_month") ?? 730,
      p95Cpu: num(meta, "p95_cpu"),
      p95Mem: num(meta, "p95_mem"),
      pricing: {
        current: readProvenance(pricing.current),
        target: readProvenance(pricing.target),
      },
    };
  }

  if (r.agent === "cost") {
    const expected = num(meta, "expected_cost");
    const actual = num(meta, "actual_cost");
    const anomalyDate = str(meta, "anomaly_date");
    if (expected === null || actual === null || !anomalyDate) return null;
    return {
      kind: "anomaly",
      service: str(meta, "service") ?? "unknown service",
      anomalyDate,
      expected,
      actual,
      delta: num(meta, "delta_usd") ?? actual - expected,
      zScore: num(meta, "z_score") ?? 0,
    };
  }

  if (r.agent === "forecast") {
    const mtd = num(meta, "current_mtd");
    const projected = num(meta, "projected_month_end");
    const budget = num(meta, "budget");
    if (mtd === null || projected === null || budget === null) return null;
    return {
      kind: "budget",
      mtd,
      projected,
      budget,
      overrunPct: num(meta, "overrun_pct") ?? 0,
    };
  }

  return null;
}

/** Render a rate at rate-card precision — $0.33 would hide a 4x difference. */
export function formatRate(amount: number, unit: PriceUnit): string {
  const suffix = unit === "hour" ? "/hr" : "/GB-month";
  return `$${amount.toFixed(4)}${suffix}`;
}

/** "14 Jul 2026" — short, unambiguous, and locale-independent for the as-of date. */
export function formatAsOf(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}
