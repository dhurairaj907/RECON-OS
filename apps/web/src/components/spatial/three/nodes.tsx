"use client";

import React, { useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Line, Edges } from "@react-three/drei";
import type { ThreePalette } from "./useThreePalette";
import type { StageStatus } from "../pipeline-model";

/* Edge brightness per state — the reference reads objects by their rim light,
   not by glow. Bodies stay matte and near-black. */
const EDGE_OPACITY: Record<StageStatus, number> = {
  pending: 0.16,
  done: 0.55,
  active: 0.95,
  blocked: 0.6,
  rejected: 0.6,
};
const EMISSIVE: Record<StageStatus, number> = {
  pending: 0.0,
  done: 0.12,
  active: 0.3,
  blocked: 0.14,
  rejected: 0.14,
};

/* ---------------- one pipeline stage ------------------------------- */

export function StageNode({
  position,
  color,
  bodyColor,
  status,
  reducedMotion,
}: {
  position: [number, number, number];
  color: THREE.Color;
  bodyColor: THREE.Color;
  status: StageStatus;
  reducedMotion: boolean;
}) {
  const group = useRef<THREE.Group>(null);
  const active = status === "active";

  useFrame((state) => {
    if (!group.current || reducedMotion) return;
    if (active) {
      const s = 1 + Math.sin(state.clock.elapsedTime * 2.4) * 0.06;
      group.current.scale.setScalar(s);
    }
    group.current.rotation.y += 0.0022;
  });

  return (
    <group ref={group} position={position}>
      <mesh castShadow={false} receiveShadow={false}>
        <octahedronGeometry args={[0.4, 0]} />
        <meshStandardMaterial
          color={bodyColor}
          emissive={color}
          emissiveIntensity={EMISSIVE[status]}
          roughness={0.62}
          metalness={0.5}
          flatShading
        />
        <Edges
          threshold={12}
          color={color}
          transparent
          opacity={EDGE_OPACITY[status]}
        />
      </mesh>
      {active && !reducedMotion && (
        <mesh scale={1.9}>
          <octahedronGeometry args={[0.4, 0]} />
          <meshBasicMaterial color={color} wireframe transparent opacity={0.14} />
        </mesh>
      )}
    </group>
  );
}

/* ---------------- connection beam --------------------------------- */

export type BeamState = "done" | "active" | "pending" | "halt";

export function ConnectionBeam({
  start,
  end,
  state,
  palette,
  reducedMotion,
}: {
  start: [number, number, number];
  end: [number, number, number];
  state: BeamState;
  palette: ThreePalette;
  reducedMotion: boolean;
}) {
  const ref = useRef<any>(null);
  const color =
    state === "done"
      ? palette.success
      : state === "active"
      ? palette.accent
      : state === "halt"
      ? palette.warning
      : palette.muted;

  useFrame((s) => {
    if (!ref.current || reducedMotion || state !== "active") return;
    const mat = ref.current.material;
    if (mat && "dashOffset" in mat) {
      mat.dashOffset = -s.clock.elapsedTime * 0.5;
    }
  });

  return (
    <Line
      ref={ref}
      points={[start, end]}
      color={color}
      lineWidth={state === "done" ? 1.6 : 1.2}
      transparent
      opacity={state === "pending" ? 0.24 : state === "halt" ? 0.45 : 0.7}
      dashed={state === "active"}
      dashScale={5}
      dashSize={0.26}
      gapSize={0.18}
    />
  );
}

/* ---------------- recovery core (matte form in a containment cube) --- */

export function RecoveryCore({
  progress,
  resolved,
  halted,
  palette,
  reducedMotion,
}: {
  progress: number; // 0..1 fraction of pipeline completed
  resolved: boolean;
  halted: boolean;
  palette: ThreePalette;
  reducedMotion: boolean;
}) {
  const inner = useRef<THREE.Mesh>(null);
  const cube = useRef<THREE.Group>(null);

  const rim = halted
    ? palette.warning
    : resolved
    ? palette.success
    : palette.accent;

  const bodyColor = useMemo(() => {
    // near-black, faintly tinted by the rim colour as progress rises
    const c = palette.bg.clone();
    c.lerp(rim, 0.06 + progress * 0.12);
    return c;
  }, [palette, progress, rim]);

  useFrame((_, delta) => {
    if (reducedMotion) return;
    if (inner.current) inner.current.rotation.y += delta * 0.16;
    if (cube.current) cube.current.rotation.y += delta * 0.03;
  });

  return (
    <group position={[0, 0.3, -2.4]}>
      {/* the recovery engine — a dark faceted form, edge-lit */}
      <mesh ref={inner}>
        <icosahedronGeometry args={[1.15, 1]} />
        <meshStandardMaterial
          color={bodyColor}
          emissive={rim}
          emissiveIntensity={0.08 + progress * (resolved ? 0.5 : 0.28)}
          roughness={0.5}
          metalness={0.55}
          flatShading
        />
        <Edges threshold={14} color={rim} transparent opacity={0.28 + progress * 0.5} />
      </mesh>

      {/* containment cube — the "vault" that holds the engine */}
      <group ref={cube}>
        <mesh scale={2.5}>
          <boxGeometry args={[1, 1, 1]} />
          <meshBasicMaterial visible={false} />
          <Edges
            threshold={1}
            color={palette.fgMuted}
            transparent
            opacity={0.14 + progress * 0.1}
          />
        </mesh>
      </group>

      <pointLight
        color={rim}
        intensity={0.35 + progress * (resolved ? 1.3 : 0.8)}
        distance={11}
        decay={2}
      />
    </group>
  );
}

/* ---------------- concentric recovery ripples ------------------------ */
/* Slow rings expanding outward from the core base — "recovery emanating
   through the network". Only when motion is allowed. */

export function ConcentricRipples({
  palette,
  active,
}: {
  palette: ThreePalette;
  active: boolean;
}) {
  const rings = useRef<THREE.Mesh[]>([]);
  const COUNT = 3;
  const MAX = 9;

  useFrame((state) => {
    if (!active) return;
    const t = state.clock.elapsedTime;
    for (let i = 0; i < COUNT; i++) {
      const m = rings.current[i];
      if (!m) continue;
      const phase = ((t * 0.12 + i / COUNT) % 1); // 0..1
      const r = 1 + phase * MAX;
      m.scale.setScalar(r);
      const mat = m.material as THREE.MeshBasicMaterial;
      mat.opacity = (1 - phase) * 0.16;
    }
  });

  return (
    <group position={[0, -1.1, -2.4]} rotation={[-Math.PI / 2, 0, 0]}>
      {Array.from({ length: COUNT }).map((_, i) => (
        <mesh
          key={i}
          ref={(el) => {
            if (el) rings.current[i] = el;
          }}
        >
          <ringGeometry args={[0.98, 1, 96]} />
          <meshBasicMaterial
            color={palette.accent}
            transparent
            opacity={0}
            side={THREE.DoubleSide}
            depthWrite={false}
          />
        </mesh>
      ))}
    </group>
  );
}

/* ---------------- ambient dust / starfield -------------------------- */

export function ActivityParticles({
  count,
  palette,
}: {
  count: number;
  palette: ThreePalette;
}) {
  const ref = useRef<THREE.Points>(null);
  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      arr[i * 3] = (Math.random() - 0.5) * 24;
      arr[i * 3 + 1] = (Math.random() - 0.5) * 11;
      arr[i * 3 + 2] = (Math.random() - 0.5) * 10 - 2;
    }
    return arr;
  }, [count]);

  useFrame((_, delta) => {
    const pts = ref.current;
    if (!pts) return;
    const arr = pts.geometry.attributes.position.array as Float32Array;
    for (let i = 0; i < count; i++) {
      arr[i * 3 + 1] += delta * 0.22;
      arr[i * 3] += delta * 0.02;
      if (arr[i * 3 + 1] > 5.5) arr[i * 3 + 1] = -5.5;
      if (arr[i * 3] > 12) arr[i * 3] = -12;
    }
    pts.geometry.attributes.position.needsUpdate = true;
  });

  if (count <= 0) return null;

  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={count}
          array={positions}
          itemSize={3}
        />
      </bufferGeometry>
      <pointsMaterial
        size={0.022}
        color={palette.fgMuted}
        transparent
        opacity={0.5}
        sizeAttenuation
        depthWrite={false}
      />
    </points>
  );
}
