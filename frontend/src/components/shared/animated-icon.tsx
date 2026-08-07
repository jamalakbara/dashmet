"use client";

import type { ComponentPropsWithoutRef } from "react";
import { motion, type HTMLMotionProps } from "framer-motion";
import type { LucideIcon, LucideProps } from "lucide-react";
import { ICON_HOVER_CLASS, ICON_MOTION, type IconMotionPreset } from "@/lib/motion";
import { cn } from "@/lib/utils";

/**
 * Wrapper that gives any lucide icon a tasteful micro-animation while honoring
 * OS reduce-motion.
 *
 * Two modes:
 *  - trigger="hover" (default): CSS `group-hover` drives the preset. The icon
 *    renders as a plain <span> carrying `group-hover:` transform classes
 *    (ICON_HOVER_CLASS in lib/motion.ts), so ANY parent container — a <Link>,
 *    <button>, row <div>, card, etc. — animates the icon when hovered, without
 *    that parent needing to be a motion component. This REQUIRES the nearest
 *    interactive/hover ancestor to carry the Tailwind `group` class; otherwise
 *    the classes are inert. reduce-motion is honored via `motion-reduce:` guards.
 *  - trigger="state": framer-motion drives the animation from a boolean `active`
 *    prop (chevron flip, pending spinners) and the `appear` mount pop. Container
 *    hover isn't needed here, so it stays a motion.span.
 *
 * The preset definitions live in lib/motion.ts (single source): ICON_MOTION
 * (framer variants, state/appear) and ICON_HOVER_CLASS (CSS classes, hover).
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
  /** className on the wrapping span. */
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

  // trigger="hover": CSS group-hover drives the animation. Rendered as a plain
  // <span> (not motion.span) so a parent container of ANY type — marked with
  // `group` — can trigger it. `rest` is HTMLMotionProps, a superset of the
  // intrinsic span attributes actually used at hover call sites; the framer-only
  // members are structurally compatible with span props (both optional) and are
  // never passed on this path.
  const spanProps = rest as ComponentPropsWithoutRef<"span">;
  return (
    <span
      className={cn("inline-flex", ICON_HOVER_CLASS[motionPreset], className)}
      {...spanProps}
    >
      <Icon className={iconClassName} size={size} aria-hidden />
    </span>
  );
}
