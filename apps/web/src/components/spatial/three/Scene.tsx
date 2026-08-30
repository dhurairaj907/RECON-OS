"use client";

import React, { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { AdaptiveDpr, AdaptiveEvents } from "@react-three/drei";
import type { PipelineStage } from "../pipeline-model";
import { usePrefersReducedMotion } from "@/hooks/usePrefersReducedMotion";
import { useSceneVisibility } from "./useSceneVisibility";
import { RecoveryCoreScene } from "./RecoveryCoreScene";

/**
 * WebGL host for the spatial pipeline. Isolated, lazy-loaded (see SpatialPipeline),
 * and cheap:
 *   - render loop is "never" whenever the canvas is off screen or the tab is hidden
 *   - dpr capped at 1.75, AdaptiveDpr drops it further under load
 *   - one core object + containment cube, ≤10 low-poly nodes, ≤220 particles,
 *     3 lights, exp fog, no postprocessing
 *   - continuous motion (rotation, ripples, particles, pointer parallax) is off
 *     under reduced-motion
 */
export default function Scene({ stages }: { stages: PipelineStage[] }) {
  const reduced = usePrefersReducedMotion();
  const { ref, active } = useSceneVisibility<HTMLDivElement>();
  const particleCount = reduced ? 0 : 220;

  return (
    <div
      ref={ref}
      className="relative h-[300px] w-full sm:h-[340px] lg:h-[380px]"
      aria-hidden="true"
    >
      <Canvas
        frameloop={active ? "always" : "never"}
        dpr={[1, 1.75]}
        camera={{ position: [0, 1.25, 12], fov: 38 }}
        gl={{ antialias: true, powerPreference: "high-performance", alpha: true }}
        style={{ background: "transparent" }}
      >
        <Suspense fallback={null}>
          <RecoveryCoreScene
            stages={stages}
            reducedMotion={reduced}
            particleCount={particleCount}
          />
        </Suspense>
        <AdaptiveDpr pixelated />
        <AdaptiveEvents />
      </Canvas>
    </div>
  );
}
