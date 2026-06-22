import { Area, AreaChart, ResponsiveContainer } from "recharts";

interface SparklineChartProps {
  data: number[];
  color?: string;
  height?: number;
}

/** A tiny axis-less sparkline used in metric cards and table rows. */
export function SparklineChart({
  data,
  color = "#0D6EFD",
  height = 40,
}: SparklineChartProps) {
  const series = data.map((value, i) => ({ i, value }));
  const gradientId = `spark-${color.replace("#", "")}`;
  if (series.length === 0) {
    return <div style={{ height }} className="w-full" />;
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={series} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.3} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          fill={`url(#${gradientId})`}
          isAnimationActive
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
