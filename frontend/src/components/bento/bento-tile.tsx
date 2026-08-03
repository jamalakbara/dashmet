"use client";

import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { fadeInUp, hoverLift } from "@/lib/motion";

interface BentoTileProps {
  /** Mono uppercase micro-label shown top-left. */
  label?: string;
  icon?: LucideIcon;
  /** Right-aligned slot in the header (e.g. a delta pill or link). */
  action?: React.ReactNode;
  /** Grid span / sizing classes (e.g. "col-span-2 row-span-2"). */
  className?: string;
  bodyClassName?: string;
  interactive?: boolean;
  children: React.ReactNode;
}

/**
 * Base bento cell: hairline-bordered near-black tile with a monospace micro-label
 * header, top hover-glow line, and entrance/hover motion. The building block for
 * the whole bento canvas.
 */
export function BentoTile({
  label,
  icon: Icon,
  action,
  className,
  bodyClassName,
  interactive = true,
  children,
}: BentoTileProps) {
  return (
    <motion.div
      variants={fadeInUp}
      {...(interactive ? hoverLift : {})}
      className={cn(
        "group relative flex flex-col overflow-hidden rounded-xl border border-border bg-card",
        "shadow-[var(--shadow-soft)] transition-colors hover:border-primary/30",
        className
      )}
    >

      {(label || action) && (
        <div className="flex items-center justify-between gap-2 px-4 pt-3">
          {label ? (
            <span className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              {Icon && <Icon className="size-3" />}
              {label}
            </span>
          ) : (
            <span />
          )}
          {action}
        </div>
      )}

      <div className={cn("flex flex-1 flex-col", bodyClassName)}>{children}</div>
    </motion.div>
  );
}
