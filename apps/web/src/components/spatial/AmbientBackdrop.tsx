"use client";

import React from "react";
import { usePrefersReducedMotion } from "@/hooks/usePrefersReducedMotion";

/**
 * Fixed, non-interactive atmospheric layer. One instance, mounted in AppShell.
 *
 *   - a volumetric top-down light cone (the "chamber lamp") + a faint accent wash
 *   - a near operational grid + a fainter far grid for parallax depth
 *   - a strong vignette so the frame reads as a chamber, not a flat page
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
      {/* volumetric top-down light cone — narrow, tall, cinematic */}
      <div
        className="absolute left-1/2 top-[-18%] h-[85vh] w-[46vw] max-w-[820px] -translate-x-1/2 blur-[90px] gpu"
        style={{
          background:
            "conic-gradient(from 180deg at 50% 0%, transparent 66deg, var(--light-cone) 90deg, var(--light-cone) 90deg, transparent 114deg)",
        }}
      />
      {/* faint accent wash at the top + a low corner wash */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(1200px 640px at 50% -14%, var(--ambient-1), transparent 62%), radial-gradient(900px 620px at 100% 100%, var(--ambient-2), transparent 55%)",
        }}
      />
      {/* far grid — fainter, larger cells */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            "linear-gradient(to right, var(--grid-line-far) 1px, transparent 1px), linear-gradient(to bottom, var(--grid-line-far) 1px, transparent 1px)",
          backgroundSize: "148px 148px",
          maskImage:
            "radial-gradient(1400px 900px at 50% 8%, rgba(0,0,0,0.6), transparent 82%)",
          WebkitMaskImage:
            "radial-gradient(1400px 900px at 50% 8%, rgba(0,0,0,0.6), transparent 82%)",
        }}
      />
      {/* near operational grid */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            "linear-gradient(to right, var(--grid-line) 1px, transparent 1px), linear-gradient(to bottom, var(--grid-line) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
          maskImage:
            "radial-gradient(1100px 760px at 50% 0%, rgba(0,0,0,0.85), transparent 78%)",
          WebkitMaskImage:
            "radial-gradient(1100px 760px at 50% 0%, rgba(0,0,0,0.85), transparent 78%)",
        }}
      />
      {/* drifting accent glow near the top */}
      <div
        className={
          "absolute -top-52 left-1/2 h-[560px] w-[760px] -translate-x-1/2 rounded-full blur-[130px] gpu" +
          (reduced ? "" : " animate-ambient-drift")
        }
        style={{ background: "var(--ambient-1)" }}
      />
      {/* strong vignette — corners sink to near-black */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(150% 130% at 50% 2%, transparent 42%, var(--vignette) 130%)",
        }}
      />
    </div>
  );
}
