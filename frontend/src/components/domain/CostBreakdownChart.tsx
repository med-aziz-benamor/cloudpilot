import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { format, parseISO } from "date-fns";

import { PROVIDER_META } from "@/lib/constants";
import { formatCurrency } from "@/lib/utils";
import type { CostTimeseriesPoint } from "@/types";

interface CostBreakdownChartProps {
  data: CostTimeseriesPoint[];
}

/** Multi-cloud daily spend area chart with three stacked provider series. */
export function CostBreakdownChart({ data }: CostBreakdownChartProps) {
  return (
    <ResponsiveContainer width="100%" height={320}>
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
        <defs>
          {(["azure", "aws", "gcp"] as const).map((p) => (
            <linearGradient key={p} id={`grad-${p}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={PROVIDER_META[p].chartColor} stopOpacity={0.3} />
              <stop offset="100%" stopColor={PROVIDER_META[p].chartColor} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" vertical={false} />
        <XAxis
          dataKey="usage_date"
          tickFormatter={(v) => format(parseISO(v), "MMM d")}
          tick={{ fontSize: 11, fill: "#94A3B8" }}
          axisLine={false}
          tickLine={false}
          minTickGap={40}
        />
        <YAxis
          tickFormatter={(v) => formatCurrency(v, { compact: true })}
          tick={{ fontSize: 11, fill: "#94A3B8" }}
          axisLine={false}
          tickLine={false}
          width={56}
        />
        <Tooltip content={<CostTooltip />} />
        <Legend
          iconType="circle"
          wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
          formatter={(v) => PROVIDER_META[v as "azure"].label}
        />
        {(["azure", "aws", "gcp"] as const).map((p) => (
          <Area
            key={p}
            type="monotone"
            dataKey={p}
            stackId="1"
            stroke={PROVIDER_META[p].chartColor}
            strokeWidth={2}
            fill={`url(#grad-${p})`}
            isAnimationActive
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}

interface TooltipPayload {
  active?: boolean;
  label?: string;
  payload?: { name: string; value: number; color: string }[];
}

function CostTooltip({ active, label, payload }: TooltipPayload) {
  if (!active || !payload?.length) return null;
  const total = payload.reduce((s, p) => s + p.value, 0);
  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-3 shadow-elevated">
      <p className="mb-2 text-caption font-semibold text-neutral-500">
        {label ? format(parseISO(label), "MMM d, yyyy") : ""}
      </p>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center justify-between gap-6 text-body-sm">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: p.color }} />
            {PROVIDER_META[p.name as "azure"].label}
          </span>
          <span className="font-semibold tabular-nums">{formatCurrency(p.value)}</span>
        </div>
      ))}
      <div className="mt-2 flex items-center justify-between border-t border-neutral-100 pt-2 text-body-sm font-semibold">
        <span>Total</span>
        <span className="tabular-nums">{formatCurrency(total)}</span>
      </div>
    </div>
  );
}
