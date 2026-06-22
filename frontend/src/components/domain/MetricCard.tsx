import { motion } from "framer-motion";
import { ArrowDownRight, ArrowUpRight, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Card } from "@/components/ui/card";
import { SparklineChart } from "@/components/domain/SparklineChart";
import { cn } from "@/lib/utils";

interface MetricCardProps {
  label: string;
  value: number;
  format: (v: number) => string;
  delta?: number;
  deltaIsGood?: (d: number) => boolean;
  icon?: LucideIcon;
  sparkline?: number[];
  sparklineColor?: string;
  sublabel?: string;
}

/** Animated KPI card with a count-up number, delta badge and sparkline. */
export function MetricCard({
  label,
  value,
  format,
  delta,
  deltaIsGood = (d) => d <= 0,
  icon: Icon,
  sparkline,
  sparklineColor = "#0D6EFD",
  sublabel,
}: MetricCardProps) {
  const display = useCountUp(value);
  const good = delta !== undefined ? deltaIsGood(delta) : true;

  return (
    <motion.div whileHover={{ y: -2 }} transition={{ duration: 0.15 }}>
      <Card className="p-5 transition-shadow duration-150 hover:shadow-card-hover">
        <div className="flex items-start justify-between">
          <p className="text-label uppercase text-neutral-400">{label}</p>
          {Icon && <Icon size={18} className="text-neutral-300" />}
        </div>
        <div className="mt-2 flex items-end gap-2">
          <span className="text-h1 font-extrabold tabular-nums text-neutral-900">
            {format(display)}
          </span>
          {delta !== undefined && (
            <span
              className={cn(
                "mb-1 inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-caption font-semibold",
                good
                  ? "bg-status-success/10 text-[#065F46]"
                  : "bg-status-danger/10 text-[#991B1B]",
              )}
            >
              {delta > 0 ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
              {Math.abs(delta).toFixed(1)}%
            </span>
          )}
        </div>
        {sublabel && <p className="mt-1 text-caption text-neutral-400">{sublabel}</p>}
        {sparkline && sparkline.length > 0 && (
          <div className="mt-3">
            <SparklineChart data={sparkline} color={sparklineColor} height={48} />
          </div>
        )}
      </Card>
    </motion.div>
  );
}

/** requestAnimationFrame count-up from 0 → target over 800ms (easeOutCubic). */
function useCountUp(target: number, duration = 800): number {
  const [value, setValue] = useState(0);
  const startRef = useRef<number | null>(null);

  useEffect(() => {
    let raf = 0;
    startRef.current = null;
    const tick = (now: number) => {
      if (startRef.current === null) startRef.current = now;
      const progress = Math.min((now - startRef.current) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(eased * target);
      if (progress < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);

  return value;
}
