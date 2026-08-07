"use client";

import { useEffect, useState } from "react";

/**
 * Tracks whether the viewport is below a breakpoint (default `md`, 768px).
 *
 * SSR-safe: starts `false` (desktop assumption) and resolves after mount, so the
 * first client render matches the server HTML and avoids a hydration mismatch.
 * Use it for behavior that must differ by size and can't be expressed in CSS
 * alone — e.g. a smaller page size on mobile so lists actually paginate.
 */
export function useIsMobile(breakpointPx = 768): boolean {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${breakpointPx - 1}px)`);
    const update = () => setIsMobile(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, [breakpointPx]);

  return isMobile;
}
