"use client";

import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * One segment in a {@link SegmentControl}. Provide either an `onValueChange`
 * handler on the group (state-based) or an `href` per item (route-based) — an
 * item with an `href` renders a Next `<Link>`, otherwise a `<button>`.
 */
export interface SegmentItem<T extends string = string> {
  value: T;
  label: string;
  icon?: LucideIcon;
  /** Route-based mode: render this segment as a link to `href`. */
  href?: string;
}

interface SegmentControlProps<T extends string> {
  items: SegmentItem<T>[];
  /** Currently-active segment value. */
  value: T;
  /** State-based mode: called with the clicked segment's value. */
  onValueChange?: (value: T) => void;
  /** `aria-label` for the segment group. */
  ariaLabel?: string;
  className?: string;
}

const CONTAINER =
  "inline-flex max-w-full items-center gap-0.5 overflow-x-auto rounded-lg bg-muted p-0.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden";
const SEGMENT_BASE =
  "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-sm whitespace-nowrap transition-colors";
const SEGMENT_ACTIVE = "bg-primary text-primary-foreground shadow-sm";
const SEGMENT_INACTIVE = "text-muted-foreground hover:text-foreground";

/**
 * The single filled-pill segmented control used app-wide. Container is a muted
 * pill; the active segment gets a solid indigo (accent) fill with
 * primary-foreground text, inactive segments are muted-foreground → foreground
 * on hover. Presentational only — owns no state.
 *
 * Supports both interaction models used in the app:
 *  - state-based: pass `value` + `onValueChange` (Day/Week/Month, Line/Bar, Grid/List)
 *  - route-based: give each item an `href` (platform tabs, settings tabs)
 */
export function SegmentControl<T extends string>({
  items,
  value,
  onValueChange,
  ariaLabel,
  className,
}: SegmentControlProps<T>) {
  return (
    <div className={cn(CONTAINER, className)} role="tablist" aria-label={ariaLabel}>
      {items.map((item) => {
        const active = item.value === value;
        const cls = cn(SEGMENT_BASE, active ? SEGMENT_ACTIVE : SEGMENT_INACTIVE);
        const Icon = item.icon;
        const content = (
          <>
            {Icon && <Icon className="size-4" />}
            {item.label}
          </>
        );

        if (item.href !== undefined) {
          return (
            <Link
              key={item.value}
              href={item.href}
              role="tab"
              aria-selected={active}
              aria-current={active ? "page" : undefined}
              className={cls}
            >
              {content}
            </Link>
          );
        }

        return (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onValueChange?.(item.value)}
            className={cls}
          >
            {content}
          </button>
        );
      })}
    </div>
  );
}
