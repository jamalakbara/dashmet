"use client";

import { useEffect } from "react";
import {
  animate,
  motion,
  useMotionValue,
  useReducedMotion,
  useTransform,
} from "framer-motion";

interface AnimatedNumberProps {
  /** Target numeric value to count up to. */
  value: number;
  /** Formatter — reuse lib/formatters.ts, never format inline. */
  format: (n: number) => string;
  className?: string;
  /** Count-up duration in seconds. */
  duration?: number;
}

/**
 * Count-up animated number. Animates from its previous value to `value` and
 * formats every frame via `format`. Respects OS "reduce motion" (settles
 * instantly). The visible text is always the formatted current frame.
 */
export function AnimatedNumber({
  value,
  format,
  className,
  duration = 0.8,
}: AnimatedNumberProps) {
  const reduce = useReducedMotion();
  const mv = useMotionValue(0);
  const text = useTransform(mv, (n) => format(n));

  useEffect(() => {
    if (reduce) {
      mv.set(value);
      return;
    }
    const controls = animate(mv, value, { duration, ease: "easeOut" });
    return () => controls.stop();
  }, [value, duration, reduce, mv]);

  return <motion.span className={className}>{text}</motion.span>;
}
