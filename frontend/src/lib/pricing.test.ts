import { describe, expect, it } from "vitest";

import { formatRate, readBasis } from "@/lib/pricing";
import type { Recommendation } from "@/types";

function rec(over: Partial<Recommendation>): Recommendation {
  return {
    id: "r1",
    agent: "rightsizing",
    title: "Underutilized resource",
    description: "",
    estimated_saving_usd: 244.46,
    confidence: 0.9,
    status: "pending",
    snoozed_until: null,
    affected_resource_ids: [],
    affected_resource_names: [],
    metadata: {},
    created_at: "2026-08-01T00:00:00Z",
    ...over,
  };
}

const FULL_RIGHTSIZING = {
  current_sku: "GP_Gen5_4",
  target_sku: "GP_Gen5_2",
  node_count: 1,
  p95_cpu: 12.4,
  p95_mem: 30.1,
  current_price_usd_hr: 0.6698,
  target_price_usd_hr: 0.3349,
  billable_hours_per_month: 730,
  pricing: {
    current: {
      rate: 0.669756,
      unit: "hour",
      currency: "USD",
      region: "westeurope",
      source: "azure_retail_api",
      meter: "SQL GP Gen5 vCore x4",
      as_of: "2026-07-14",
    },
    target: {
      rate: 0.334878,
      unit: "hour",
      currency: "USD",
      region: "westeurope",
      source: "azure_retail_api",
      meter: "SQL GP Gen5 vCore x2",
      as_of: "2026-07-14",
    },
  },
};

describe("readBasis", () => {
  it("reads a full rightsizing basis with both rates' provenance", () => {
    const basis = readBasis(rec({ metadata: FULL_RIGHTSIZING }));

    expect(basis).toMatchObject({ kind: "rightsizing", currentSku: "GP_Gen5_4" });
    // The full-precision catalog rate, not the agent's rounded display copy.
    expect(basis).toMatchObject({ pricing: { current: { rate: 0.669756 } } });
  });

  it("returns null when the metadata carries no basis at all", () => {
    // Rows written before the agent recorded one. Showing a "how this was
    // calculated" disclosure that opens onto nothing is worse than showing none.
    expect(readBasis(rec({ metadata: {} }))).toBeNull();
  });

  it("still returns the basis when provenance is missing, marking it absent", () => {
    const basis = readBasis(
      rec({ metadata: { ...FULL_RIGHTSIZING, pricing: undefined } }),
    );
    expect(basis).toMatchObject({ kind: "rightsizing" });
    expect(basis).toMatchObject({ pricing: { current: null, target: null } });
  });

  it("rejects a provenance record missing the fields that make it traceable", () => {
    const noSource = {
      ...FULL_RIGHTSIZING,
      pricing: {
        current: { rate: 0.669756, unit: "hour", region: "westeurope" },
        target: FULL_RIGHTSIZING.pricing.target,
      },
    };
    const basis = readBasis(rec({ metadata: noSource }));
    // A rate with no publisher and no as-of date cannot be judged, so it is not
    // presented as attributed.
    expect(basis).toMatchObject({ pricing: { current: null } });
    expect(basis).toMatchObject({ pricing: { target: { source: "azure_retail_api" } } });
  });

  it("rejects an unrecognised price source rather than rendering a blank badge", () => {
    const basis = readBasis(
      rec({
        metadata: {
          ...FULL_RIGHTSIZING,
          pricing: {
            current: { ...FULL_RIGHTSIZING.pricing.current, source: "vibes" },
            target: FULL_RIGHTSIZING.pricing.target,
          },
        },
      }),
    );
    expect(basis).toMatchObject({ pricing: { current: null } });
  });

  it("keys on the agent, not on the shape of the metadata", () => {
    // Rightsizing-shaped metadata under a cost recommendation must not be read as
    // a rate derivation — that would label one agent's numbers with another's.
    const basis = readBasis(rec({ agent: "cost", metadata: FULL_RIGHTSIZING }));
    expect(basis).toBeNull();
  });

  it("reads the cost agent's anomaly basis", () => {
    const basis = readBasis(
      rec({
        agent: "cost",
        metadata: {
          anomaly_date: "2026-08-14",
          service: "virtualmachines",
          expected_cost: 120.5,
          actual_cost: 640.0,
          delta_usd: 519.5,
          z_score: 6.2,
        },
      }),
    );
    expect(basis).toMatchObject({ kind: "anomaly", zScore: 6.2, actual: 640 });
  });

  it("reads the forecast agent's budget basis", () => {
    const basis = readBasis(
      rec({
        agent: "forecast",
        metadata: {
          current_mtd: 4200.0,
          projected_month_end: 8277.0,
          budget: 7500.0,
          overrun_pct: 10.4,
        },
      }),
    );
    expect(basis).toMatchObject({ kind: "budget", budget: 7500, overrunPct: 10.4 });
  });

  it("returns null for the architect agent, which quotes no derived figure", () => {
    expect(readBasis(rec({ agent: "architect", metadata: { anything: 1 } }))).toBeNull();
  });
});

describe("formatRate", () => {
  it("keeps rate-card precision", () => {
    // $0.33 and $0.3349 look alike; over 730 hours they are $12/month apart.
    expect(formatRate(0.334878, "hour")).toBe("$0.3349/hr");
  });

  it("labels storage per GB-month, never per hour", () => {
    expect(formatRate(0.0208, "gb_month")).toBe("$0.0208/GB-month");
  });
});
