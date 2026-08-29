"use client";

import React, { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { usePrefersReducedMotion } from "@/hooks/usePrefersReducedMotion";

interface AnimatedNumberProps {
  /** Target value. Strings are parsed as floats (backend sends decimal strings). */
  value: number | string;
  /** Render the tweened number to a string. Default: locale integer. */
  format?: (n: number) => string;
  /** Tween duration in ms. */
  duration?: number;
  className?: string;
  as?: keyof JSX.IntrinsicElements;
}

const toNum = (v: number | string): number => {
  const n = typeof v === "string" ? parseFloat(v) : v;
  return Number.isFinite(n) ? n : 0;
};

const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);

/**
 * Counts from the previous value to the next one whenever `value` actually
 * changes — a real backend update, not a re-render. `tabular-nums` keeps the
 * width stable so nothing jitters. Under `prefers-reduced-motion` it snaps
 * instantly. The displayed number is always the true current/target value on
 * settle, never an approximation.
 */
export function AnimatedNumber({
  value,
  format = (n) => Math.round(n).toLocaleString(),
  duration = 650,
  className,
  as = "span",
}: AnimatedNumberProps) {
  const Tag = as as any;
  const reduced = usePrefersReducedMotion();
  const target = toNum(value);
  const [display, setDisplay] = useState(target);
  const fromRef = useRef(target);
  const rafRef = useRef<number | null>(null);
  const startRef = useRef(0);

  useEffect(() => {
    if (reduced || duration <= 0) {
      setDisplay(target);
      fromRef.current = target;
      return;
    }
    const from = fromRef.current;
    if (from === target) return;
    startRef.current = performance.now();

    const tick = (now: number) => {
      const t = Math.min(1, (now - startRef.current) / duration);
      const eased = easeOut(t);
      setDisplay(from + (target - from) * eased);
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        setDisplay(target);
        fromRef.current = target;
        rafRef.current = null;
      }
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      fromRef.current = target;
    };
  }, [target, duration, reduced]);

  return (
    <Tag className={cn("tabular-nums", className)}>{format(display)}</Tag>
  );
}
