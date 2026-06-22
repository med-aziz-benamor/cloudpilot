import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { format, parseISO } from "date-fns";

import { formatCurrency } from "@/lib/utils";
import type { ForecastResponse } from "@/types";

interface ForecastChartProps {
  forecast: ForecastResponse;
}

/** Actuals (solid) + forecast (dashed) + confidence band + budget line. */
export function ForecastChart({ forecast }: ForecastChartProps) {
  const actualMap = new Map(forecast.actuals.map((a) => [a.ds, a.y]));
  const dates = [
    ...forecast.actuals.map((a) => a.ds),
    ...forecast.points.map((p) => p.ds),
  ];
  const data = dates.map((ds) => {
    const fc = forecast.points.find((p) => p.ds === ds);
    return {
      ds,
      actual: actualMap.get(ds) ?? null,
      yhat: fc?.yhat ?? null,
      band: fc ? [fc.yhat_lower, fc.yhat_upper] : null,
    };
  });

  return (
    <ResponsiveContainer width="100%" height={380}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 8 }}>
        <defs>
          <linearGradient id="band" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0D6EFD" stopOpacity={0.18} />
            <stop offset="100%" stopColor="#0D6EFD" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" vertical={false} />
        <XAxis
          dataKey="ds"
          tickFormatter={(v) => format(parseISO(v), "MMM d")}
          tick={{ fontSize: 11, fill: "#94A3B8" }}
          axisLine={false}
          tickLine={false}
          minTickGap={48}
        />
        <YAxis
          tickFormatter={(v) => formatCurrency(v, { compact: true })}
          tick={{ fontSize: 11, fill: "#94A3B8" }}
          axisLine={false}
          tickLine={false}
          width={56}
        />
        <Tooltip
          formatter={(v: number) => formatCurrency(v)}
          labelFormatter={(v) => format(parseISO(String(v)), "MMM d, yyyy")}
          contentStyle={{
            borderRadius: 12,
            border: "1px solid #E2E8F0",
            boxShadow: "0 8px 32px rgba(10,22,40,.16)",
            fontSize: 12,
          }}
        />
        <Area
          type="monotone"
          dataKey="band"
          stroke="none"
          fill="url(#band)"
          isAnimationActive
        />
        <Line
          type="monotone"
          dataKey="actual"
          stroke="#0F172A"
          strokeWidth={2.5}
          dot={false}
          name="Actual"
          connectNulls
        />
        <Line
          type="monotone"
          dataKey="yhat"
          stroke="#0D6EFD"
          strokeWidth={2}
          strokeDasharray="6 4"
          dot={false}
          name="Forecast"
          connectNulls
        />
        <ReferenceLine
          y={forecast.budget_usd}
          stroke="#EF4444"
          strokeDasharray="4 4"
          label={{ value: "Budget", fontSize: 11, fill: "#EF4444", position: "right" }}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
