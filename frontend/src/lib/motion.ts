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
