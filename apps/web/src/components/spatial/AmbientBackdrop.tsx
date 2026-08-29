"use client";

import React from "react";
import { usePrefersReducedMotion } from "@/hooks/usePrefersReducedMotion";

/**
 * Fixed, non-interactive atmospheric layer. One instance, mounted in AppShell.
 *
 *   - two static radial gradients (token-driven, theme-aware)
 *   - a near operational grid + a fainter far grid for parallax depth
 *   - a soft vignette so the frame reads as a chamber, not a flat page
 *   - one slow-drifting accent glow (frozen under reduced-motion)
 *
 * Never competes with data: opacity is low, colours are near-background.
 */
export function AmbientBackdrop() {
  const reduced = usePrefersReducedMotion();

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-0 overflow-hidden"
    >
      {/* base radial washes */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(1100px 620px at 50% -12%, var(--ambient-1), transparent 60%), radial-gradient(900px 600px at 100% 100%, var(--ambient-2), transparent 55%)",
        }}
      />
      {/* far grid — fainter, larger cells */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            "linear-gradient(to right, var(--grid-line-far) 1px, transparent 1px), linear-gradient(to bottom, var(--grid-line-far) 1px, transparent 1px)",
          backgroundSize: "132px 132px",
          maskImage:
            "radial-gradient(1400px 900px at 50% 10%, rgba(0,0,0,0.7), transparent 85%)",
          WebkitMaskImage:
            "radial-gradient(1400px 900px at 50% 10%, rgba(0,0,0,0.7), transparent 85%)",
        }}
      />
      {/* near operational grid */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            "linear-gradient(to right, var(--grid-line) 1px, transparent 1px), linear-gradient(to bottom, var(--grid-line) 1px, transparent 1px)",
          backgroundSize: "56px 56px",
          maskImage:
            "radial-gradient(1200px 800px at 50% 0%, rgba(0,0,0,0.9), transparent 80%)",
          WebkitMaskImage:
            "radial-gradient(1200px 800px at 50% 0%, rgba(0,0,0,0.9), transparent 80%)",
        }}
      />
      {/* drifting accent glow */}
      <div
        className={
          "absolute -top-40 left-1/2 h-[520px] w-[820px] -translate-x-1/2 rounded-full blur-[120px] gpu" +
          (reduced ? "" : " animate-ambient-drift")
        }
        style={{ background: "var(--ambient-1)" }}
      />
      {/* vignette */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(140% 120% at 50% 0%, transparent 55%, var(--vignette) 140%)",
        }}
      />
    </div>
  );
}
