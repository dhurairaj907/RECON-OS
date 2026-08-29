"use client";

import { useCallback, useEffect, useRef } from "react";
import { usePrefersReducedMotion } from "./usePrefersReducedMotion";

interface Options {
  /** Max rotation in degrees on each axis. */
  max?: number;
  /** Disable entirely (e.g. mobile timeline mode). */
  disabled?: boolean;
}

/**
 * Subtle cursor-follow tilt for a 3D plane.
 *
 * - rAF-coalesced, `pointermove` is `passive`
 * - no-op on coarse pointers (touch) and when reduced-motion is set
 * - listener only lives while the element is on screen
 * - writes CSS vars `--rx` / `--ry` (degrees) on the target element
 */
export function usePointerParallax<T extends HTMLElement>({
  max = 3,
  disabled = false,
}: Options = {}) {
  const ref = useRef<T | null>(null);
  const frame = useRef<number | null>(null);
  const reduced = usePrefersReducedMotion();

  const reset = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.setProperty("--rx", "0deg");
    el.style.setProperty("--ry", "0deg");
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const coarse = window.matchMedia("(pointer: coarse)").matches;
    if (disabled || reduced || coarse) {
      reset();
      return;
    }

    let visible = false;

    const onMove = (e: PointerEvent) => {
      if (!visible) return;
      if (frame.current != null) return;
      frame.current = requestAnimationFrame(() => {
        frame.current = null;
        const rect = el.getBoundingClientRect();
        const px = (e.clientX - rect.left) / rect.width - 0.5;
        const py = (e.clientY - rect.top) / rect.height - 0.5;
        el.style.setProperty("--ry", `${(px * max).toFixed(2)}deg`);
        el.style.setProperty("--rx", `${(-py * max).toFixed(2)}deg`);
      });
    };

    const io = new IntersectionObserver(
      ([entry]) => {
        visible = entry.isIntersecting;
        if (!visible) reset();
      },
      { threshold: 0.15 }
    );
    io.observe(el);

    window.addEventListener("pointermove", onMove, { passive: true });
    el.addEventListener("pointerleave", reset);

    return () => {
      io.disconnect();
      window.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", reset);
      if (frame.current != null) cancelAnimationFrame(frame.current);
      frame.current = null;
    };
  }, [max, disabled, reduced, reset]);

  return ref;
}
