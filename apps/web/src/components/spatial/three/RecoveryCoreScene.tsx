"use client";

import React, { useMemo } from "react";
import { Html } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import type { PipelineStage } from "../pipeline-model";
import { useThreePalette } from "./useThreePalette";
import {
  StageNode,
  ConnectionBeam,
  RecoveryCore,
  ConcentricRipples,
  ActivityParticles,
  type BeamState,
} from "./nodes";

function beamState(a: PipelineStage, b: PipelineStage): BeamState {
  if (a.status === "blocked" || a.status === "rejected") return "halt";
  if (a.status === "done" && b.status === "done") return "done";
  if (a.status === "done" && b.status === "active") return "active";
  if (a.status === "done") return "done";
  return "pending";
}

interface Props {
  stages: PipelineStage[];
  reducedMotion: boolean;
  particleCount: number;
}

/**
 * The RECON recovery pipeline as a spatial object: a dark faceted "recovery
 * engine" held in a wireframe containment cube, with the pipeline stages as
 * edge-lit nodes receding along a shallow arc. Colour, emission and beam state
 * come straight from the shared `PipelineStage[]` model — the same real-data
 * derivation the CSS pipeline uses. Nothing here invents state.
 */
export function RecoveryCoreScene({ stages, reducedMotion, particleCount }: Props) {
  const palette = useThreePalette();
  const { scene } = useThree();

  // subtle pointer parallax on the whole rig
  useFrame((state) => {
    if (reducedMotion) return;
    state.camera.position.x +=
      (state.pointer.x * 0.9 - state.camera.position.x) * 0.03;
    state.camera.position.y +=
      (1.25 + state.pointer.y * 0.5 - state.camera.position.y) * 0.03;
    state.camera.lookAt(0, 0.15, -1);
    scene.rotation.y += (state.pointer.x * 0.1 - scene.rotation.y) * 0.04;
    scene.rotation.x += (state.pointer.y * -0.05 - scene.rotation.x) * 0.04;
  });

  const layout = useMemo(() => {
    const n = stages.length;
    return stages.map((s, i) => {
      const t = n > 1 ? i / (n - 1) : 0.5;
      const x = (t - 0.5) * 12.5;
      const y = Math.sin(t * Math.PI) * 0.4 + Math.sin(i * 1.7) * 0.1;
      const z = -Math.cos(t * Math.PI) * 0.8;
      return { stage: s, pos: [x, y, z] as [number, number, number] };
    });
  }, [stages]);

  const progress = useMemo(() => {
    if (!stages.length) return 0;
    return stages.filter((s) => s.status === "done").length / stages.length;
  }, [stages]);

  const resolved = stages[stages.length - 1]?.status === "done";
  const active = layout.find((l) => l.stage.status === "active");
  const halted = !!stages.find(
    (s) => s.status === "blocked" || s.status === "rejected"
  );

  return (
    <>
      {/* bg-matched fog so distant nodes sink into the chamber */}
      <fogExp2
        attach="fog"
        args={[palette.bg.getHex(), palette.isDark ? 0.05 : 0.03]}
      />

      {/* chamber lamp: one strong key from top, dim back rim, low fill */}
      <ambientLight intensity={palette.isDark ? 0.22 : 0.55} />
      <directionalLight
        position={[0.5, 8, 3]}
        intensity={palette.isDark ? 1.1 : 1.3}
        color={"#eef0ff"}
      />
      <directionalLight
        position={[-6, -1, -5]}
        intensity={0.3}
        color={palette.accent}
      />

      <RecoveryCore
        progress={progress}
        resolved={resolved}
        halted={halted}
        palette={palette}
        reducedMotion={reducedMotion}
      />

      <ConcentricRipples palette={palette} active={!reducedMotion} />

      {layout.slice(0, -1).map((l, i) => (
        <ConnectionBeam
          key={`beam-${l.stage.key}`}
          start={l.pos}
          end={layout[i + 1].pos}
          state={beamState(l.stage, layout[i + 1].stage)}
          palette={palette}
          reducedMotion={reducedMotion}
        />
      ))}

      {layout.map((l) => (
        <StageNode
          key={l.stage.key}
          position={l.pos}
          color={palette.status[l.stage.status]}
          bodyColor={palette.body}
          status={l.stage.status}
          reducedMotion={reducedMotion}
        />
      ))}

      {active && (
        <Html
          position={[active.pos[0], active.pos[1] + 0.9, active.pos[2]]}
          center
          distanceFactor={11}
          zIndexRange={[20, 0]}
          style={{ pointerEvents: "none" }}
        >
          <div className="whitespace-nowrap rounded-md border border-accent/40 bg-surface/85 px-2 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-accent backdrop-blur-sm">
            {active.stage.label}
            {active.stage.value ? ` · ${active.stage.value}` : ""}
          </div>
        </Html>
      )}

      <Html
        position={[0, -2.9, -2.4]}
        center
        distanceFactor={12}
        style={{ pointerEvents: "none" }}
      >
        <div
          className={
            "whitespace-nowrap rounded-md border px-2.5 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.18em] backdrop-blur-sm " +
            (resolved
              ? "border-status-success-border bg-status-success-bg text-status-success"
              : halted
              ? "border-status-warning-border bg-status-warning-bg text-status-warning"
              : "border-hairline bg-surface/85 text-fg-secondary")
          }
        >
          {resolved
            ? "RECOVERY VERIFIED"
            : halted
            ? "PIPELINE HELD"
            : `RECOVERY CORE · ${Math.round(progress * 100)}%`}
        </div>
      </Html>

      <ActivityParticles count={particleCount} palette={palette} />
    </>
  );
}
