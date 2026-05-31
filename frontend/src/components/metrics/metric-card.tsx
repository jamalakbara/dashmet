"use client";

import { LineChart, Line, ResponsiveContainer } from "recharts";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { formatChange } from "@/lib/formatters";

interface MetricCardProps {
  label: string;
  value: string;
  change?: number | null;
  sparkline?: number[];
  loading?: boolean;
}

export function MetricCard({ label, value, change, sparkline, loading }: MetricCardProps) {
  if (loading) {
    return (
      <Card>
        <CardContent className="p-4 space-y-2">
          <div className="h-3 w-20 animate-pulse rounded bg-muted" />
          <div className="h-6 w-28 animate-pulse rounded bg-muted" />
          <div className="h-3 w-16 animate-pulse rounded bg-muted" />
        </CardContent>
      </Card>
    );
  }

  const { label: changeLabel, direction } = formatChange(change);
  const sparkData = (sparkline ?? []).map((v) => ({ v }));

  const TrendIcon =
    direction === "up" ? TrendingUp : direction === "down" ? TrendingDown : Minus;

  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          {label}
        </p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>

        <div className="mt-2 flex items-center justify-between">
          {change != null ? (
            <span
              className={cn(
                "inline-flex items-center gap-1 text-xs font-medium",
                direction === "up" && "text-green-600",
                direction === "down" && "text-red-500",
                direction === "neutral" && "text-muted-foreground"
              )}
            >
              <TrendIcon className="size-3" />
              {changeLabel}
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">—</span>
          )}

          {sparkData.length > 1 && (
            <div className="h-8 w-20">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={sparkData}>
                  <Line
                    type="monotone"
                    dataKey="v"
                    dot={false}
                    strokeWidth={1.5}
                    stroke={direction === "down" ? "#ef4444" : "#2563eb"}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
