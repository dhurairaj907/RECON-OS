"use client";

import React from "react";

export type GlowTone = "idle" | "info" | "success" | "warning" | "danger";

/**
 * A fixed, state-tinted radial wash behind the app. Communicates the dominant
 * operational state without shouting: a faint emerald bloom when revenue was just
 * recovered, red when a critical case is open, amber while work is pending, blue
 * while the pipeline is processing. Colour + opacity come from theme tokens
 * (`--glow-*`); the position is static so reduced-motion is unaffected.
 *
 * Mounted once in AppShell; the tone is derived from real backend data by each
 * page and passed down (never a decorative default beyond "idle").
 */
export function AtmosphericGlow({ tone = "idle" }: { tone?: GlowTone }) {
  return <div aria-hidden="true" className="atmo-glow" data-tone={tone} />;
}
