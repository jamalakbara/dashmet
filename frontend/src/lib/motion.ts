/**
 * Single source of truth for framer-motion variants + transitions (DRY).
 * Import these instead of re-declaring animation objects in components.
 * All motion honors OS "reduce motion" via <MotionConfig reducedMotion="user">
 * (set in components/shared/providers.tsx).
 */
import type { Variants } from "framer-motion";

/** Shared snappy spring. */
export const SPRING = { type: "spring", stiffness: 400, damping: 32 } as const;

/** Fade + rise. Use as a child variant under `staggerContainer`. */
export const fadeInUp: Variants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: "easeOut" } },
};

/** Parent container that staggers its children's entrance. */
export const staggerContainer: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.05, delayChildren: 0.02 } },
};

/** Spread onto a motion element for a playful hover lift.
 *  Pair with `shadow-soft hover:shadow-lift transition-shadow` classes so the
 *  colored shadow swaps on hover alongside the translate. */
export const hoverLift = {
  whileHover: { y: -4, transition: SPRING },
  whileTap: { scale: 0.99 },
} as const;

/** Standard mount props for a staggered list/grid. */
export const staggerGrid = {
  variants: staggerContainer,
  initial: "hidden" as const,
  animate: "show" as const,
};

/** Standard mount props for a single fade-in element. */
export const fadeInProps = {
  variants: fadeInUp,
  initial: "hidden" as const,
  animate: "show" as const,
};

/* ───────────────────────── Icon micro-animations ─────────────────────────
 * Presets consumed by <AnimatedIcon> (components/shared/animated-icon.tsx).
 * Each is a framer-motion `Variants` map with a `rest` + one or more trigger
 * states, so the same object drives whileHover/whileTap or animate-on-state.
 * All honor OS reduce-motion via the global <MotionConfig reducedMotion="user">.
 */

/** Snappy transition tuned for small glyph movement. */
export const ICON_SPRING = { type: "spring", stiffness: 500, damping: 24 } as const;

/** Named presets — keep this the single list the primitive + docs reference. */
export type IconMotionPreset =
  | "spin"
  | "wiggle"
  | "bounce"
  | "pop"
  | "draw"
  | "nudge"
  | "nudgeRight"
  | "flip";

/** 90° tip on hover — for settings/config glyphs (gears, sliders). */
export const iconSpin: Variants = {
  rest: { rotate: 0 },
  hover: { rotate: 90, transition: ICON_SPRING },
  tap: { rotate: 90, scale: 0.9 },
};

/** Playful side-to-side shake on hover — bells, alerts, attention glyphs. */
export const iconWiggle: Variants = {
  rest: { rotate: 0 },
  hover: {
    rotate: [0, -12, 10, -6, 0],
    transition: { duration: 0.5, ease: "easeInOut" },
  },
  tap: { scale: 0.9 },
};

/** A quick vertical hop — downloads/exports, "arriving" trend arrows. */
export const iconBounce: Variants = {
  rest: { y: 0 },
  hover: {
    y: [0, 2, -1, 0],
    transition: { duration: 0.4, ease: "easeInOut" },
  },
  tap: { y: 1, scale: 0.9 },
};

/** Scale pop from nothing — mount emphasis for badges/state icons; also a
 *  hover heartbeat (stars, checks, add actions). */
export const iconPop: Variants = {
  rest: { scale: 1 },
  hidden: { scale: 0, opacity: 0 },
  show: { scale: 1, opacity: 1, transition: ICON_SPRING },
  hover: { scale: 1.18, transition: ICON_SPRING },
  tap: { scale: 0.85 },
};

/** Stroke-draw on mount, subtle pulse on hover — external-link / plug glyphs. */
export const iconDraw: Variants = {
  rest: { scale: 1, opacity: 1 },
  hidden: { scale: 0.6, opacity: 0 },
  show: { scale: 1, opacity: 1, transition: ICON_SPRING },
  hover: { scale: 1.12, rotate: 8, transition: ICON_SPRING },
  tap: { scale: 0.9 },
};

/** Slide a touch to the right on hover — "go / navigate / see more" chevrons. */
export const iconNudgeRight: Variants = {
  rest: { x: 0 },
  hover: { x: 3, transition: ICON_SPRING },
  tap: { x: 1, scale: 0.9 },
};

/** Small lift on hover — generic nav/menu action glyphs. */
export const iconNudge: Variants = {
  rest: { y: 0, scale: 1 },
  hover: { y: -1, scale: 1.12, transition: ICON_SPRING },
  tap: { scale: 0.9 },
};

/** 180° flip — expand/collapse chevrons. Drive with trigger="state" + `active`
 *  and activeVariant="hover". */
export const iconFlip: Variants = {
  rest: { rotate: 0 },
  hover: { rotate: 180, transition: ICON_SPRING },
  tap: { rotate: 180, scale: 0.9 },
};

/** Lookup used by <AnimatedIcon> to resolve a preset name → variants. */
export const ICON_MOTION: Record<IconMotionPreset, Variants> = {
  spin: iconSpin,
  wiggle: iconWiggle,
  bounce: iconBounce,
  pop: iconPop,
  draw: iconDraw,
  nudge: iconNudge,
  nudgeRight: iconNudgeRight,
  flip: iconFlip,
};
