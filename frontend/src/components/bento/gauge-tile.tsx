"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { BentoTile } from "./bento-tile";
import { AnimatedNumber } from "@/components/shared/animated-number";
import { irisGradientDef } from "@/lib/chart-theme";

interface GaugeTileProps {
  label: string;
  icon?: LucideIcon;
  className?: string;
  /** 0..1 arc fill. */
  fraction: number;
  /** Center numeral (count-up). */
  value: number;
  format: (n: number) => string;
  unit?: string;
  footerLeft?: string;
  footerRight?: string;
  loading?: boolean;
}

const R = 95;
const CX = 110;
const CY = 120;
// Semicircle over the top, from left (15,120) to right (205,120).
const ARC = `M ${CX - R},${CY} A ${R},${R} 0 0 1 ${CX + R},${CY}`;

/** Radial gauge with an iridescent value arc and a count-up center numeral. */
export function GaugeTile({
  label,
  icon,
  className,
  fraction,
  value,
  format,
  unit,
  footerLeft,
  footerRight,
  loading,
}: GaugeTileProps) {
  const reduce = useReducedMotion();
  const f = Math.max(0, Math.min(1, Number.isFinite(fraction) ? fraction : 0));
  const theta = Math.PI * (1 - f);
  const knobX = CX + R * Math.cos(theta);
  const knobY = CY - R * Math.sin(theta);
  const gid = `gauge-iris-${label.replace(/\W+/g, "")}`;

  return (
    <BentoTile label={label} icon={icon} className={className}>
      <div className="flex flex-1 flex-col justify-end px-4 pb-3">
        <div className="flex flex-col items-center">
          {loading ? (
            <div className="h-10 w-24 animate-pulse rounded bg-muted" />
          ) : (
            <div className="font-display text-4xl font-semibold tabular-nums leading-none">
              <AnimatedNumber value={value} format={format} />
            </div>
          )}
          {unit && (
            <div className="mt-1 font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
              {unit}
            </div>
          )}
        </div>

        <svg viewBox="0 0 220 132" className="mt-2 w-full">
          <defs>{irisGradientDef(gid)}</defs>
          <path
            d={ARC}
            fill="none"
            stroke="var(--border)"
            strokeWidth={10}
            strokeLinecap="round"
          />
          <motion.path
            d={ARC}
            fill="none"
            stroke={`url(#${gid})`}
            strokeWidth={10}
            strokeLinecap="round"
            initial={{ pathLength: reduce ? f : 0 }}
            animate={{ pathLength: f }}
            transition={{ duration: 1.1, ease: "easeOut" }}
          />
          {!loading && (
            <circle
              cx={knobX}
              cy={knobY}
              r={6}
              fill="var(--foreground)"
              stroke="var(--card)"
              strokeWidth={3}
            />
          )}
        </svg>

        {(footerLeft || footerRight) && (
          <div className="flex items-center justify-between font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
            <span>{footerLeft}</span>
            <span>{footerRight}</span>
          </div>
        )}
      </div>
    </BentoTile>
  );
}
