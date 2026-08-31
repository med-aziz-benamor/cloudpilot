import { TooltipProvider } from "@radix-ui/react-tooltip";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CalculationBasis } from "@/components/domain/CalculationBasis";
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

const prov = (source: string, sku: string) => ({
  rate: sku === "GP_Gen5_4" ? 0.669756 : 0.334878,
  unit: "hour",
  currency: "USD",
  region: "westeurope",
  source,
  meter: `SQL ${sku}`,
  as_of: "2026-07-14",
});

const RIGHTSIZING = {
  current_sku: "GP_Gen5_4",
  target_sku: "GP_Gen5_2",
  node_count: 1,
  current_price_usd_hr: 0.6698,
  target_price_usd_hr: 0.3349,
  billable_hours_per_month: 730,
  pricing: {
    current: prov("azure_retail_api", "GP_Gen5_4"),
    target: prov("azure_retail_api", "GP_Gen5_2"),
  },
};

function show(r: Recommendation) {
  render(
    <TooltipProvider>
      <CalculationBasis recommendation={r} />
    </TooltipProvider>,
  );
}

describe("CalculationBasis", () => {
  it("is collapsed until asked for", () => {
    show(rec({ metadata: RIGHTSIZING }));
    expect(screen.queryByText(/GP_Gen5_4/)).not.toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: /how this saving was calculated/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("GP_Gen5_4")).toBeInTheDocument();
  });

  it("shows the arithmetic reconciling to the saving on the card", () => {
    show(rec({ metadata: RIGHTSIZING }));
    fireEvent.click(screen.getByRole("button"));

    // Rates at rate-card precision, the hours, and the headline figure itself —
    // so the derivation visibly multiplies out to the number being acted on.
    expect(screen.getByText(/\$0\.6698\/hr.*\$0\.3349\/hr.*730 h/s)).toBeInTheDocument();
    expect(screen.getByText(/\$244/)).toBeInTheDocument();
  });

  it("multiplies the saving across a node pool", () => {
    show(rec({ metadata: { ...RIGHTSIZING, node_count: 4 }, estimated_saving_usd: 977.85 }));
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText(/× 4 nodes/)).toBeInTheDocument();
  });

  it("names the publisher behind each rate", () => {
    show(rec({ metadata: RIGHTSIZING }));
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getAllByText("Azure Retail API")).toHaveLength(2);
    expect(screen.getByText(/quoted as of 14 Jul 2026/i)).toBeInTheDocument();
  });

  it("flags a transcribed list price as not machine-verified", () => {
    show(
      rec({
        metadata: {
          ...RIGHTSIZING,
          pricing: {
            current: prov("published_list_price", "GP_Gen5_4"),
            target: prov("published_list_price", "GP_Gen5_2"),
          },
        },
      }),
    );
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText(/Both rates are a published list price/i)).toBeInTheDocument();
  });

  it("says so when a rate has no recorded source", () => {
    show(rec({ metadata: { ...RIGHTSIZING, pricing: {} } }));
    fireEvent.click(screen.getByRole("button"));
    // An unattributed rate must not look the same as an attributed one.
    expect(screen.getAllByText(/source not recorded/i)).toHaveLength(2);
  });

  it("renders nothing at all for a recommendation with no recorded basis", () => {
    const { container } = render(
      <TooltipProvider>
        <CalculationBasis recommendation={rec({ metadata: {} })} />
      </TooltipProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("explains a cost anomaly from billed amounts, not from the rate card", () => {
    show(
      rec({
        agent: "cost",
        estimated_saving_usd: null,
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
    fireEvent.click(screen.getByRole("button", { name: /what triggered this/i }));
    expect(screen.getByText(/Expected virtualmachines spend/)).toBeInTheDocument();
    expect(screen.getByText("6.2σ")).toBeInTheDocument();
    expect(screen.getByText(/not from the rate card/i)).toBeInTheDocument();
  });

  it("shows the budget a forecast alert was measured against", () => {
    show(
      rec({
        agent: "forecast",
        estimated_saving_usd: null,
        metadata: {
          current_mtd: 4200,
          projected_month_end: 8277,
          budget: 7500,
          overrun_pct: 10.4,
        },
      }),
    );
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("$7,500")).toBeInTheDocument();
    expect(screen.getByText("10.4%")).toBeInTheDocument();
  });
});
