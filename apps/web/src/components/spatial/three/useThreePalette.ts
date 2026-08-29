"use client";

import { useEffect, useMemo, useState } from "react";
import * as THREE from "three";
import { useTheme } from "@/lib/theme";
import type { StageStatus } from "../pipeline-model";

export interface ThreePalette {
  bg: THREE.Color;
  accent: THREE.Color;
  success: THREE.Color;
  warning: THREE.Color;
  danger: THREE.Color;
  muted: THREE.Color;
  /** Per-status node colour. */
  status: Record<StageStatus, THREE.Color>;
  isDark: boolean;
}

function readVar(name: string, fallback: string): THREE.Color {
  if (typeof window === "undefined") return new THREE.Color(fallback);
  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  // tokens are "R G B" triplets
  const m = raw.match(/^(\d+)\s+(\d+)\s+(\d+)$/);
  if (m) return new THREE.Color(`rgb(${m[1]}, ${m[2]}, ${m[3]})`);
  return new THREE.Color(fallback);
}

/**
 * Bridges the CSS semantic theme tokens into three.js `Color`s so the 3D scene
 * tracks light/dark exactly like the rest of the app. Re-reads whenever the
 * effective theme flips (after the CSS transition settles).
 */
export function useThreePalette(): ThreePalette {
  const { effective } = useTheme();
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const id = window.setTimeout(() => setTick((t) => t + 1), 220);
    return () => window.clearTimeout(id);
  }, [effective]);

  return useMemo(() => {
    const accent = readVar("--c-accent", "#2563eb");
    const success = readVar("--c-success", "#34d399");
    const warning = readVar("--c-warning", "#fbbf24");
    const danger = readVar("--c-danger", "#fb7185");
    const muted = readVar("--c-fg-faint", "#64748b");
    const bg = readVar("--c-bg", "#0b0e14");
    return {
      bg,
      accent,
      success,
      warning,
      danger,
      muted,
      isDark: effective === "dark",
      status: {
        done: success,
        active: accent,
        pending: muted,
        blocked: warning,
        rejected: danger,
      },
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effective, tick]);
}
