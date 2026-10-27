import { AlertTriangle, ArrowDown, ChevronDown, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  formatAsOf,
  formatRate,
  PRICE_SOURCE_META,
  readBasis,
  type RightsizingBasis,
} from "@/lib/pricing";
import { cn, formatCurrency } from "@/lib/utils";
import type { PricingProvenance, Recommendation } from "@/types";

/**
 * The derivation behind a recommendation's headline number, on demand.
 *
 * The backend has always tracked where each rate came from; until now it stopped at
 * the database. A saving a reviewer cannot trace back to a published rate is a
 * number they have to trust, which is precisely what a FinOps tool must not ask.
 *
 * Collapsed by default: the feed is scanned, and the derivation only matters at the
 * moment someone is deciding whether to act on one card.
 */
export function CalculationBasis({ recommendation: r }: { recommendation: Recommendation }) {
  const [open, setOpen] = useState(false);
  const basis = readBasis(r);

  // No basis recorded (an older row, or an agent that stores none) — say nothing
  // rather than showing an empty "how this was calculated" that opens onto air.
  if (!basis) return null;

  const label =
    basis.kind === "rightsizing" ? "How this saving was calculated" : "What triggered this";

  return (
    <div className="mt-3 border-t border-neutral-100 pt-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-1 text-caption font-medium text-neutral-500 transition-colors hover:text-brand-primary"
      >
        <ChevronDown
          size={13}
          className={cn("transition-transform", open && "rotate-180")}
          aria-hidden
        />
        {label}
      </button>

      {open && (
        <div className="mt-2 rounded-md bg-neutral-50 p-3 text-caption text-neutral-600">
          {basis.kind === "rightsizing" && (
            <RightsizingDerivation basis={basis} savingUsd={r.estimated_saving_usd} />
          )}

          {basis.kind === "anomaly" && (
            <dl className="space-y-1">
              <Row label={`Expected ${basis.service} spend`}>
                {formatCurrency(basis.expected)}
              </Row>
              <Row label={`Actually billed on ${basis.anomalyDate}`}>
                {formatCurrency(basis.actual)}
              </Row>
              <Row label="Deviation from the 30-day baseline">
                {basis.zScore.toFixed(1)}σ
              </Row>
              <p className="pt-1 text-neutral-500">
                Derived from billed amounts, not from the rate card.
              </p>
            </dl>
          )}

          {basis.kind === "budget" && (
            <dl className="space-y-1">
              <Row label="Spend month-to-date">{formatCurrency(basis.mtd)}</Row>
              <Row label="Projected month-end">{formatCurrency(basis.projected)}</Row>
              <Row label="Monthly budget">{formatCurrency(basis.budget)}</Row>
              <Row label="Projected overrun">{basis.overrunPct.toFixed(1)}%</Row>
            </dl>
          )}
        </div>
      )}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-neutral-500">{label}</dt>
      <dd className="font-mono tabular-nums text-neutral-800">{children}</dd>
    </div>
  );
}

function RightsizingDerivation({
  basis,
  savingUsd,
}: {
  basis: RightsizingBasis;
  savingUsd: number | null;
}) {
  // Prefer the provenance rate: it is the catalog's full-precision figure, while the
  // agent's own copy is rounded for display and would not multiply out to the cent.
  const current = basis.pricing.current?.rate ?? basis.currentRate;
  const target = basis.pricing.target?.rate ?? basis.targetRate;
  const unit = basis.pricing.current?.unit ?? "hour";
  const scale = basis.nodeCount > 1 ? ` × ${basis.nodeCount} nodes` : "";

  const asOf = basis.pricing.current?.as_of ?? basis.pricing.target?.as_of ?? null;
  const rates = [basis.pricing.current, basis.pricing.target].filter(
    (p): p is PricingProvenance => p !== null,
  );
  const unverified = rates.filter((p) => !PRICE_SOURCE_META[p.source].verified);

  return (
    <div className="space-y-2">
      <div className="space-y-1">
        <RateLine sku={basis.currentSku} rate={current} unit={unit} prov={basis.pricing.current} />
        <div className="flex items-center gap-1 pl-1 text-neutral-400">
          <ArrowDown size={11} aria-hidden />
          <span>downsize to</span>
        </div>
        <RateLine sku={basis.targetSku} rate={target} unit={unit} prov={basis.pricing.target} />
      </div>

      <p className="border-t border-neutral-200 pt-2 font-mono tabular-nums text-neutral-800">
        ({formatRate(current, unit)} − {formatRate(target, unit)}) ×{" "}
        {basis.hoursPerMonth} h{scale} ={" "}
        <span className="font-semibold text-status-success">
          {savingUsd === null ? "—" : formatCurrency(savingUsd)}/month
        </span>
      </p>

      {asOf && (
        <p className="text-neutral-500">
          Rates quoted as of {formatAsOf(asOf)}.
        </p>
      )}

      {unverified.length > 0 && (
        <p className="flex items-start gap-1.5 text-[#92400E]">
          <AlertTriangle size={12} className="mt-0.5 shrink-0" aria-hidden />
          <span>
            {unverified.length === rates.length ? "Both rates are" : "One rate is"} a
            published list price, transcribed rather than fetched from a provider API.
          </span>
        </p>
      )}
    </div>
  );
}

function RateLine({
  sku,
  rate,
  unit,
  prov,
}: {
  sku: string;
  rate: number;
  unit: PricingProvenance["unit"];
  prov: PricingProvenance | null;
}) {
  const meta = prov ? PRICE_SOURCE_META[prov.source] : null;

  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
      <span className="font-mono text-neutral-800">{sku}</span>
      <span className="font-mono tabular-nums text-neutral-800">
        {formatRate(rate, unit)}
      </span>
      {meta && prov ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              className={cn(
                "inline-flex cursor-help items-center gap-1 rounded-full px-1.5 py-0.5 text-[11px] font-medium",
                meta.verified
                  ? "bg-status-success/10 text-status-success"
                  : "bg-status-warning/10 text-[#92400E]",
              )}
            >
              {meta.verified && <ShieldCheck size={10} aria-hidden />}
              {meta.label}
            </span>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-[260px]">
            {meta.detail}
            {prov.meter && ` Meter: ${prov.meter}.`}
          </TooltipContent>
        </Tooltip>
      ) : (
        // The agent priced this SKU but recorded no provenance for it. Saying so is
        // the point: an unattributed rate should look different from an attributed one.
        <span className="rounded-full bg-neutral-200 px-1.5 py-0.5 text-[11px] text-neutral-600">
          source not recorded
        </span>
      )}
      {prov && <span className="text-neutral-400">{prov.region}</span>}
    </div>
  );
}
