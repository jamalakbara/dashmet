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
 * Base bento cell: standard card surface (bg-card, hairline ring, soft shadow) —
 * the same visual language as the platform overview cards — with a sans
 * muted-foreground micro-label header and entrance/hover motion. The building
 * block for the whole bento canvas.
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
        "group relative flex flex-col overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10",
        "shadow-[var(--shadow-soft)] transition-shadow hover:shadow-[var(--shadow-lift)]",
        className
      )}
    >

      {(label || action) && (
        <div className="flex items-center justify-between gap-2 px-4 pt-4">
          {label ? (
            <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              {Icon && <Icon className="size-3.5" />}
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
