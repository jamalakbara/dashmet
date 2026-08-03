"use client";

import { motion, type HTMLMotionProps } from "framer-motion";
import type { LucideIcon, LucideProps } from "lucide-react";
import { ICON_MOTION, type IconMotionPreset } from "@/lib/motion";
import { cn } from "@/lib/utils";

/**
 * Wrapper that gives any lucide icon a tasteful micro-animation while honoring
 * OS reduce-motion (framer-motion's global <MotionConfig reducedMotion="user">
 * neutralizes every transform below when the user asks for less motion, so no
 * per-call guard is needed).
 *
 * Two modes:
 *  - trigger="hover" (default): plays the preset on hover/tap of the icon (or,
 *    with `group`, the nearest `.group` ancestor — e.g. a whole button/link).
 *  - trigger="state": drives the animation from a boolean `active` prop — used
 *    for expand/collapse (chevron rotate), pending spinners, and appear pops.
 *
 * The preset variants live in lib/motion.ts (single source), keyed by name.
 */
export interface AnimatedIconProps
  extends Omit<HTMLMotionProps<"span">, "children"> {
  /** The lucide glyph to render. */
  icon: LucideIcon;
  /** Animation preset name (see lib/motion.ts ICON_MOTION). */
  motionPreset: IconMotionPreset;
  /** How the animation is triggered. Default "hover". */
  trigger?: "hover" | "state";
  /**
   * For trigger="state": which variant to hold while active. "hover" replays
   * the hover keyframes; "show" pops in; "rest" is the idle state. Defaults to
   * "hover".
   */
  activeVariant?: "hover" | "show" | "tap" | "rest";
  /** For trigger="state": whether the active variant is currently applied. */
  active?: boolean;
  /**
   * For trigger="state" appear animations: run the "hidden"→"show" mount pass.
   * Ignored for hover triggers.
   */
  appear?: boolean;
  /** Props forwarded to the underlying lucide icon (className, size, etc.). */
  iconClassName?: string;
  size?: LucideProps["size"];
  /** className on the wrapping motion.span. */
  className?: string;
}

export function AnimatedIcon({
  icon: Icon,
  motionPreset,
  trigger = "hover",
  activeVariant = "hover",
  active = false,
  appear = false,
  iconClassName,
  size,
  className,
  ...rest
}: AnimatedIconProps) {
  const variants = ICON_MOTION[motionPreset];

  if (trigger === "state") {
    return (
      <motion.span
        className={cn("inline-flex", className)}
        variants={variants}
        initial={appear ? "hidden" : "rest"}
        animate={active ? activeVariant : appear ? "show" : "rest"}
        {...rest}
      >
        <Icon className={iconClassName} size={size} aria-hidden />
      </motion.span>
    );
  }

  return (
    <motion.span
      className={cn("inline-flex", className)}
      variants={variants}
      initial="rest"
      animate="rest"
      whileHover="hover"
      whileTap="tap"
      {...rest}
    >
      <Icon className={iconClassName} size={size} aria-hidden />
    </motion.span>
  );
}
