"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Globe } from "lucide-react";
import { DashCard } from "@/components/shared/dash-card";
import { insightsApi } from "@/lib/api/insights";
import { queryKeys } from "@/lib/query-keys";
import { irisColor } from "@/lib/chart-theme";
import type { DateRange } from "@/lib/query-keys";

/** Rough country centroids (ISO-2 → [lat, lon]). Enough to plot the usual spread. */
const CENTROIDS: Record<string, [number, number]> = {
  US: [38, -97], CA: [56, -106], MX: [23, -102], BR: [-14, -51], AR: [-38, -63],
  CL: [-35, -71], CO: [4, -72], GB: [54, -2], IE: [53, -8], FR: [46, 2],
  DE: [51, 10], ES: [40, -4], PT: [39, -8], IT: [42, 12], NL: [52, 5],
  BE: [50, 4], CH: [47, 8], AT: [47, 14], SE: [62, 15], NO: [62, 10],
  DK: [56, 9], FI: [64, 26], PL: [52, 19], TR: [39, 35], RU: [61, 90],
  IN: [21, 78], CN: [35, 103], JP: [36, 138], KR: [36, 128], SG: [1, 104],
  ID: [-2, 118], MY: [4, 102], TH: [15, 101], PH: [13, 122], VN: [16, 108],
  AE: [24, 54], SA: [24, 45], ZA: [-29, 24], NG: [9, 8], EG: [26, 30],
  AU: [-25, 134], NZ: [-41, 173],
};

const W = 560;
const H = 240;
const project = (lat: number, lon: number): [number, number] => [
  ((lon + 180) / 360) * W,
  ((90 - lat) / 180) * H,
];

// Static dot-grid backdrop (reads as a world surface).
const DOTS: [number, number][] = [];
for (let y = 12; y < H; y += 15) {
  for (let x = 12; x < W; x += 15) DOTS.push([x, y]);
}

interface BreakdownRow {
  breakdown_value: string;
  dimensions: Record<string, string>;
  metrics: Record<string, number>;
}

interface GeoTileProps {
  className?: string;
  /** When set, fetches country breakdown for this account and plots it. */
  accountId?: string;
  dateRange: DateRange;
  caption?: string;
}

/** Signature geo tile: dotted world grid + spend-weighted country points, mono
 *  coordinate pills, and an arc between the top two markets. */
export function GeoTile({ className, accountId, dateRange, caption }: GeoTileProps) {
  const { data: res } = useQuery({
    queryKey: queryKeys.breakdown(accountId ?? "", dateRange, "country"),
    queryFn: () =>
      insightsApi.breakdown({
        account_id: accountId!,
        ...dateRange,
        breakdown_type: "country",
        level: "account",
      }),
    enabled: !!accountId,
    staleTime: 30 * 60 * 1000,
  });

  const points = useMemo(() => {
    const rows: BreakdownRow[] = res?.data?.data?.rows ?? [];
    return rows
      .map((r) => {
        const code = (r.dimensions.country ?? r.breakdown_value ?? "").toUpperCase();
        const c = CENTROIDS[code];
        if (!c) return null;
        const [x, y] = project(c[0], c[1]);
        return { code, lat: c[0], lon: c[1], x, y, spend: r.metrics.spend ?? 0 };
      })
      .filter((p): p is NonNullable<typeof p> => p != null)
      .sort((a, b) => b.spend - a.spend)
      .slice(0, 6);
  }, [res]);

  const top = points[0];
  const second = points[1];
  const arc =
    top && second
      ? `M ${top.x},${top.y} Q ${(top.x + second.x) / 2},${
          Math.min(top.y, second.y) - 60
        } ${second.x},${second.y}`
      : null;

  return (
    <DashCard
      title={caption ?? "Geo reach"}
      icon={Globe}
      accent="bg-sky-500"
      className={className}
    >
      <div className="relative flex-1 px-2 pb-2">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="h-full w-full"
          preserveAspectRatio="xMidYMid meet"
        >
          {/* dotted world grid */}
          {DOTS.map(([x, y], i) => (
            <circle key={i} cx={x} cy={y} r={1} className="fill-muted-foreground/25" />
          ))}

          {/* arc between top two markets */}
          {arc && (
            <motion.path
              d={arc}
              fill="none"
              stroke={irisColor(3)}
              strokeWidth={1.25}
              strokeDasharray="3 4"
              initial={{ pathLength: 0, opacity: 0 }}
              animate={{ pathLength: 1, opacity: 0.9 }}
              transition={{ duration: 1.2, ease: "easeOut" }}
            />
          )}

          {/* country points */}
          {points.map((p, i) => {
            const color = irisColor(i);
            return (
              <g key={p.code}>
                {i === 0 && (
                  <motion.circle
                    cx={p.x}
                    cy={p.y}
                    r={4}
                    fill={color}
                    initial={{ opacity: 0.5, scale: 1 }}
                    animate={{ opacity: [0.5, 0, 0.5], scale: [1, 3, 1] }}
                    transition={{ duration: 2.4, repeat: Infinity, ease: "easeOut" }}
                    style={{ transformOrigin: `${p.x}px ${p.y}px` }}
                  />
                )}
                <circle cx={p.x} cy={p.y} r={3} fill={color} />
              </g>
            );
          })}
        </svg>

        {/* coordinate pills for the top 3 markets */}
        <div className="pointer-events-none absolute inset-0">
          {points.slice(0, 3).map((p) => (
            <span
              key={p.code}
              className="absolute -translate-x-1/2 -translate-y-full rounded-full bg-card/80 px-1.5 py-0.5 text-[9px] text-muted-foreground ring-1 ring-foreground/10 backdrop-blur"
              style={{
                left: `${(p.x / W) * 100}%`,
                top: `${(p.y / H) * 100}%`,
              }}
            >
              {p.code} {p.lat.toFixed(1)}°,{p.lon.toFixed(1)}°
            </span>
          ))}
        </div>
      </div>
    </DashCard>
  );
}
