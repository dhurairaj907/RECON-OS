"use client";

import React, { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { cn } from "@/lib/utils";
import { usePrefersReducedMotion } from "@/hooks/usePrefersReducedMotion";
import type { PipelineStage } from "../pipeline-model";
import { RecoveryPipeline3D } from "../RecoveryPipeline3D";
import { isWebGLAvailable } from "./webgl";

const Scene = dynamic(() => import("./Scene"), {
  ssr: false,
  loading: () => (
    <div className="h-[300px] w-full animate-pulse rounded-lg bg-surface-subtle/40 sm:h-[340px] lg:h-[420px]" />
  ),
});

/** True only where the cinematic WebGL field is worth mounting. */
export function useSpatialFieldEnabled(): boolean {
  const reduced = usePrefersReducedMotion();
  const [ok, setOk] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const update = () => setOk(mq.matches && !reduced && isWebGLAvailable());
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, [reduced]);
  return ok;
}

/**
 * Just the WebGL recovery field (no chrome). Returns null when it shouldn't
 * mount — callers pair it with the CSS `RecoveryPipeline3D` panel for the real,
 * accessible detail. Used edge-bleed inside the Command Center hero banner.
 */
export function SpatialField({
  stages,
  className,
}: {
  stages: PipelineStage[];
  className?: string;
}) {
  const enabled = useSpatialFieldEnabled();
  if (!enabled) return null;
  return (
    <div className={cn("h-full w-full", className)} aria-hidden="true">
      <Scene stages={stages} />
    </div>
  );
}

interface Props {
  stages: PipelineStage[];
  title?: string;
  caption?: string;
  className?: string;
}

/**
 * Public spatial-pipeline entry point.
 *
 *   desktop (≥1024) + motion allowed + WebGL  → cinematic 3D field ABOVE the
 *                                               full CSS/SVG pipeline panel
 *   otherwise                                 → the CSS/SVG pipeline alone
 *
 * The CSS pipeline (real `<ol>`/`<li>` text, per-stage values, provenance) is
 * always present, so the experience degrades cleanly and stays accessible; the
 * WebGL layer is a purely visual, `aria-hidden` enhancement.
 */
export function SpatialPipeline({ stages, title, caption, className }: Props) {
  const enabled = useSpatialFieldEnabled();

  if (!enabled) {
    return (
      <RecoveryPipeline3D
        stages={stages}
        title={title}
        caption={caption}
        className={className}
      />
    );
  }

  return (
    <div className={cn("space-y-3", className)}>
      <div className="relative overflow-hidden rounded-2xl border border-border bg-surface/40 depth-highlight backdrop-blur-sm">
        <div className="pointer-events-none absolute left-5 top-4 z-10 label-mono">
          Spatial Recovery Field · live
        </div>
        <SpatialField stages={stages} />
      </div>
      <RecoveryPipeline3D stages={stages} title={title} caption={caption} />
    </div>
  );
}
