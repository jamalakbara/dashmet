"use client";

import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { fadeInUp } from "@/lib/motion";
import { CardChipHeader } from "@/components/shared/card-chip-header";

interface DashCardProps {
  /** Chip-header title. When set (with `icon`) renders the shared `CardChipHeader`. */
  title?: string;
  icon?: LucideIcon;
  /** Tailwind bg color for the header icon chip (e.g. "bg-orange-500"). */
  accent?: string;
  /** Right-aligned header slot (e.g. a "See Detail" link). */
  action?: React.ReactNode;
  /** Grid span / sizing classes (e.g. "lg:col-span-2"). */
  className?: string;
  /** Extra classes for the body wrapper that holds `children`. */
  bodyClassName?: string;
  children: React.ReactNode;
}

/**
 * The one dashboard card. A single card surface (`bg-card`, hairline ring, soft
 * shadow) with an entrance animation and — deliberately — **no hover motion or
 * shadow swap**, matching the platform overview cards. Every card on every
 * dashboard page renders through this (directly, or via `MetricGroupCard` /
 * `CombinedKpiCard`, which are built on it), so surfaces never drift again.
 */
export function DashCard({
  title,
  icon: Icon,
  accent,
  action,
  className,
  bodyClassName,
  children,
}: DashCardProps) {
  return (
    <motion.div
      variants={fadeInUp}
      className={cn(
        "flex flex-col overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10 shadow-[var(--shadow-soft)]",
        className,
      )}
    >
      {title && Icon && (
        <div className="px-5 pt-5">
          <CardChipHeader icon={Icon} title={title} accent={accent} action={action} />
        </div>
      )}
      <div className={cn("flex flex-1 flex-col", bodyClassName)}>{children}</div>
    </motion.div>
  );
}
