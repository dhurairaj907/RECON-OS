"use client";

import React, { useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Line } from "@react-three/drei";
import type { ThreePalette } from "./useThreePalette";
import type { StageStatus } from "../pipeline-model";

const EMISSIVE: Record<StageStatus, number> = {
  pending: 0.12,
  done: 0.55,
  active: 1.1,
  blocked: 0.6,
  rejected: 0.6,
};

/* ---------------- one pipeline stage ------------------------------- */

export function StageNode({
  position,
  color,
  status,
  reducedMotion,
}: {
  position: [number, number, number];
  color: THREE.Color;
  status: StageStatus;
  reducedMotion: boolean;
}) {
  const group = useRef<THREE.Group>(null);
  const active = status === "active";

  useFrame((state) => {
    if (!group.current || reducedMotion) return;
    if (active) {
      const s = 1 + Math.sin(state.clock.elapsedTime * 3) * 0.08;
      group.current.scale.setScalar(s);
    }
    group.current.rotation.y += 0.003;
  });

  return (
    <group ref={group} position={position}>
      <mesh>
        <octahedronGeometry args={[0.4, 0]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={EMISSIVE[status]}
          roughness={0.34}
          metalness={0.12}
          flatShading
        />
      </mesh>
      {/* technical wire shell */}
      <mesh scale={1.42}>
        <octahedronGeometry args={[0.4, 0]} />
        <meshBasicMaterial
          color={color}
          wireframe
          transparent
          opacity={active ? 0.4 : status === "pending" ? 0.12 : 0.22}
        />
      </mesh>
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
      mat.dashOffset = -s.clock.elapsedTime * 0.6;
    }
  });

  return (
    <Line
      ref={ref}
      points={[start, end]}
      color={color}
      lineWidth={state === "done" ? 2 : 1.4}
      transparent
      opacity={state === "pending" ? 0.32 : state === "halt" ? 0.5 : 0.85}
      dashed={state === "active"}
      dashScale={5}
      dashSize={0.28}
      gapSize={0.16}
    />
  );
}

/* ---------------- recovery core ---------------------------------- */

export function RecoveryCore({
  progress,
  resolved,
  palette,
  reducedMotion,
}: {
  progress: number; // 0..1 fraction of pipeline completed
  resolved: boolean;
  palette: ThreePalette;
  reducedMotion: boolean;
}) {
  const inner = useRef<THREE.Mesh>(null);
  const outer = useRef<THREE.Group>(null);

  const emissiveColor = useMemo(() => {
    const c = palette.muted.clone();
    c.lerp(resolved ? palette.success : palette.accent, 0.25 + progress * 0.75);
    return c;
  }, [palette, progress, resolved]);

  useFrame((state, delta) => {
    if (reducedMotion) return;
    if (inner.current) inner.current.rotation.y += delta * 0.18;
    if (outer.current) {
      outer.current.rotation.y -= delta * 0.12;
      outer.current.rotation.x += delta * 0.05;
    }
  });

  return (
    <group position={[0, 0.35, -2.6]}>
      <mesh ref={inner}>
        <icosahedronGeometry args={[1.3, 1]} />
        <meshStandardMaterial
          color={palette.bg}
          emissive={emissiveColor}
          emissiveIntensity={0.18 + progress * 0.9}
          roughness={0.28}
          metalness={0.35}
          flatShading
        />
      </mesh>
      <group ref={outer}>
        <mesh scale={1.7}>
          <icosahedronGeometry args={[1.3, 0]} />
          <meshBasicMaterial
            color={resolved ? palette.success : palette.accent}
            wireframe
            transparent
            opacity={0.12 + progress * 0.18}
          />
        </mesh>
      </group>
      <pointLight
        color={resolved ? palette.success : palette.accent}
        intensity={0.5 + progress * 1.6}
        distance={12}
        decay={2}
      />
    </group>
  );
}

/* ---------------- ambient activity particles -------------------- */

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
      arr[i * 3] = (Math.random() - 0.5) * 20;
      arr[i * 3 + 1] = (Math.random() - 0.5) * 9;
      arr[i * 3 + 2] = (Math.random() - 0.5) * 8 - 2;
    }
    return arr;
  }, [count]);

  useFrame((_, delta) => {
    const pts = ref.current;
    if (!pts) return;
    const arr = pts.geometry.attributes.position.array as Float32Array;
    for (let i = 0; i < count; i++) {
      arr[i * 3 + 1] += delta * 0.35;
      if (arr[i * 3 + 1] > 4.5) arr[i * 3 + 1] = -4.5;
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
        size={0.035}
        color={palette.muted}
        transparent
        opacity={0.55}
        sizeAttenuation
        depthWrite={false}
      />
    </points>
  );
}
