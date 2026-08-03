"use client";

import { AreaChart, Area, ResponsiveContainer } from "recharts";
import { motion } from "framer-motion";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { Card } from "@/components/ui/card";
import { AnimatedNumber } from "@/components/shared/animated-number";
import { cn } from "@/lib/utils";
import { formatChange } from "@/lib/formatters";
import { fadeInUp, hoverLift } from "@/lib/motion";
import { AnimatedIcon } from "@/components/shared/animated-icon";
import { chartAnimation } from "@/lib/chart-theme";

/** Pastel tints (registered in globals.css @theme). Round-robin across cards. */
export const TINTS = ["mint", "lilac", "peach", "sky", "butter", "blush"] as const;
export type Tint = (typeof TINTS)[number];

const TINT_BG: Record<Tint, string> = {
  mint: "bg-tint-mint",
  lilac: "bg-tint-lilac",
  peach: "bg-tint-peach",
  sky: "bg-tint-sky",
  butter: "bg-tint-butter",
  blush: "bg-tint-blush",
};

/** CSS var for each tint's deep hue — used for the dot + sparkline (Gestalt: a
 *  single hue codes each metric across its dot and its trend line). */
const TINT_VAR: Record<Tint, string> = {
  mint: "var(--tint-mint-fg)",
  lilac: "var(--tint-lilac-fg)",
  peach: "var(--tint-peach-fg)",
  sky: "var(--tint-sky-fg)",
  butter: "var(--tint-butter-fg)",
  blush: "var(--tint-blush-fg)",
};

export const tintByIndex = (i: number): Tint => TINTS[i % TINTS.length];

interface MetricCardProps {
  label: string;
  /** Pre-formatted display value (fallback / loading). */
  value: string;
  /** Raw numeric value — when provided with `format`, the value counts up. */
  numericValue?: number | null;
  /** Formatter for the count-up (reuse lib/formatters.ts). */
  format?: (n: number) => string;
  change?: number | null;
  sparkline?: number[];
  tint?: Tint;
  loading?: boolean;
}

export function MetricCard({
  label,
  value,
  numericValue,
  format,
  change,
  sparkline,
  tint,
  loading,
}: MetricCardProps) {
  if (loading) {
    return (
      <Card className="overflow-hidden shadow-[var(--shadow-soft)]">
        <div className="space-y-3 p-4">
          <div className="h-3 w-24 animate-pulse rounded bg-muted" />
          <div className="h-8 w-28 animate-pulse rounded bg-muted" />
        </div>
        <div className="h-10 w-full animate-pulse bg-muted/50" />
      </Card>
    );
  }

  const { label: changeLabel, direction } = formatChange(change);
  const sparkData = (sparkline ?? []).map((v) => ({ v }));
  const doAnimate = numericValue != null && format != null;
  const hue = tint ? TINT_VAR[tint] : "var(--primary)";
  const gid = `spark-${label.replace(/\W+/g, "")}`;

  const TrendIcon =
    direction === "up" ? TrendingUp : direction === "down" ? TrendingDown : Minus;

  return (
    <motion.div variants={fadeInUp} {...hoverLift}>
      <Card
        className={cn(
          "gap-0 overflow-hidden py-0 shadow-[var(--shadow-soft)] transition-shadow hover:shadow-[var(--shadow-lift)]",
          tint && TINT_BG[tint]
        )}
      >
        {/* Header: label + colored dot (left) · delta pill (right) */}
        <div className="px-4 pt-4">
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <span
                className="size-2 rounded-full"
                style={{ backgroundColor: hue }}
              />
              {label}
            </span>

            {change != null ? (
              <span
                className={cn(
                  "inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[11px] font-semibold",
                  direction === "up" &&
                    "bg-emerald-500/12 text-emerald-600 dark:text-emerald-400",
                  direction === "down" && "bg-red-500/12 text-red-500",
                  direction === "neutral" && "bg-muted text-muted-foreground"
                )}
              >
                <AnimatedIcon
                  icon={TrendIcon}
                  motionPreset="pop"
                  trigger="state"
                  appear
                  activeVariant="show"
                  iconClassName="size-3"
                />
                {changeLabel}
              </span>
            ) : null}
          </div>

          {/* Hero value */}
          <div className="mt-2 font-display text-3xl font-semibold tabular-nums">
            {doAnimate ? (
              <AnimatedNumber value={numericValue!} format={format!} />
            ) : (
              value
            )}
          </div>
        </div>

        {/* Full-bleed hue-coded sparkline */}
        <div className="mt-3 h-10">
          {sparkData.length > 1 ? (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={sparkData} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={hue} stopOpacity={0.35} />
                    <stop offset="100%" stopColor={hue} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <Area
                  type="monotone"
                  dataKey="v"
                  stroke={hue}
                  strokeWidth={1.75}
                  fill={`url(#${gid})`}
                  dot={false}
                  {...chartAnimation}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : null}
        </div>
      </Card>
    </motion.div>
  );
}
