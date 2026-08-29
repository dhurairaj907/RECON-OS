"use client";

import React from "react";
import {
  Zap,
  BrainCircuit,
  TrendingUp,
  Route,
  ShieldCheck,
  Send,
  CreditCard,
  CheckCircle2,
  ShieldAlert,
  FlaskConical,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { usePrefersReducedMotion } from "@/hooks/usePrefersReducedMotion";
import { usePointerParallax } from "@/hooks/usePointerParallax";
import {
  STATUS_META,
  type PipelineStage,
  type StageStatus,
} from "./pipeline-model";
import { FlowConnector, type ConnectorState } from "./FlowConnector";

const ICONS: Record<string, LucideIcon> = {
  event: Zap,
  diagnosis: BrainCircuit,
  prediction: TrendingUp,
  strategy: Route,
  policy: ShieldCheck,
  action: Send,
  razorpay: CreditCard,
  recovered: CheckCircle2,
};

const Z: Record<StageStatus, number> = {
  active: 42,
  done: 16,
  blocked: 26,
  rejected: 26,
  pending: 4,
};

function connectorState(a: PipelineStage, b: PipelineStage): ConnectorState {
  if (a.status === "blocked" || a.status === "rejected") return "halt";
  if (a.status === "done" && b.status === "done") return "done";
  if (a.status === "done" && b.status === "active") return "active";
  if (a.status === "done") return "done";
  return "pending";
}

/* ---------- provenance chip ------------------------------------------ */

function ProvenanceChip({ stage }: { stage: PipelineStage }) {
  if (!stage.provenance) return null;
  const simulated = stage.provenance === "simulated";
  const Icon = simulated ? FlaskConical : ShieldCheck;
  return (
    <span
      className={cn(
        "mt-1 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] font-mono font-bold uppercase tracking-wider border",
        simulated
          ? "border-dashed border-status-warning text-status-warning bg-status-warning-bg"
          : "border-status-success text-status-success bg-status-success-bg"
      )}
    >
      <Icon className="h-2.5 w-2.5" />
      {simulated ? "Simulated" : "Verified"}
    </span>
  );
}

/* ---------- one node ------------------------------------------------- */

function PipelineNode({
  stage,
  spatial,
}: {
  stage: PipelineStage;
  spatial: boolean;
}) {
  const meta = STATUS_META[stage.status];
  const Icon = ICONS[stage.key] ?? ShieldAlert;
  const simulated = stage.provenance === "simulated";

  return (
    <li
      aria-current={stage.status === "active" ? "step" : undefined}
      className="relative flex flex-col items-center text-center"
      style={
        spatial
          ? {
              transform: `translateZ(${Z[stage.status]}px)`,
              transformStyle: "preserve-3d",
            }
          : undefined
      }
    >
      <div
        className={cn(
          "relative z-10 flex h-11 w-11 items-center justify-center rounded-xl border bg-surface transition-colors",
          meta.ring,
          stage.status === "active" && "shadow-depth-hover",
          simulated && "border-dashed"
        )}
      >
        <Icon className={cn("h-4 w-4", meta.text)} />
        {stage.status === "active" && (
          <span className="motion-safe-only absolute -inset-0.5 rounded-xl border border-accent/60 animate-pulse-node" />
        )}
      </div>

      <div className="mt-2 text-[10px] font-mono font-semibold uppercase tracking-wider text-fg-secondary">
        {stage.label}
      </div>
      <div
        className={cn(
          "mt-0.5 text-[11px] font-mono font-medium tabular-nums max-w-[130px] truncate",
          meta.text
        )}
        title={stage.value}
      >
        {stage.value ?? "—"}
      </div>
      {stage.sub && (
        <div
          className="mt-0.5 text-[9px] font-mono text-fg-faint max-w-[130px] truncate"
          title={stage.sub}
        >
          {stage.sub}
        </div>
      )}
      <ProvenanceChip stage={stage} />
      {stage.note && (
        <div
          className={cn(
            "mt-0.5 text-[9px] font-mono max-w-[132px] leading-tight",
            simulated ? "text-status-warning" : "text-fg-faint"
          )}
        >
          {stage.note}
        </div>
      )}
      <span className="sr-only">status: {meta.label}</span>
    </li>
  );
}

/* ---------- horizontal graph (desktop 3D / tablet flat) ------------- */

function HorizontalGraph({
  stages,
  spatial,
  animate,
  label,
}: {
  stages: PipelineStage[];
  spatial: boolean;
  animate: boolean;
  label: string;
}) {
  const parallaxRef = usePointerParallax<HTMLDivElement>({
    disabled: !spatial,
    max: 3,
  });
  const total = stages.length;
  const width = total * 100;

  return (
    <div
      className={cn(
        spatial ? "perspective-1600" : "",
        !spatial && "overflow-x-auto"
      )}
    >
      <div
        ref={parallaxRef}
        className={cn(
          "relative min-w-[720px] px-2 pb-2 pt-1",
          spatial && "preserve-3d transition-transform duration-300 ease-spatial"
        )}
        style={
          spatial
            ? {
                transform:
                  "rotateX(calc(7deg + var(--rx, 0deg))) rotateY(var(--ry, 0deg))",
              }
            : undefined
        }
      >
        {/* connector layer sits behind the icon tiles */}
        <svg
          aria-hidden="true"
          viewBox={`0 0 ${width} 56`}
          preserveAspectRatio="none"
          className="absolute inset-x-2 top-1 h-[44px]"
          style={spatial ? { transform: "translateZ(6px)" } : undefined}
        >
          {stages.slice(0, -1).map((s, i) => (
            <FlowConnector
              key={s.key}
              id={s.key}
              x1={(i + 0.5) * 100}
              x2={(i + 1.5) * 100}
              y={28}
              state={connectorState(s, stages[i + 1])}
              animate={animate}
            />
          ))}
        </svg>

        <ol
          aria-label={label}
          className="relative grid gap-2"
          style={{ gridTemplateColumns: `repeat(${total}, minmax(0, 1fr))` }}
        >
          {stages.map((s) => (
            <PipelineNode key={s.key} stage={s} spatial={spatial} />
          ))}
        </ol>
      </div>
    </div>
  );
}

/* ---------- timeline (mobile / reduced-motion) --------------------- */

function TimelineGraph({
  stages,
  label,
}: {
  stages: PipelineStage[];
  label: string;
}) {
  return (
    <ol aria-label={label} className="relative space-y-1 pl-6">
      <span className="absolute left-[9px] top-2 bottom-2 w-px bg-border-highlight" />
      {stages.map((s) => {
        const meta = STATUS_META[s.status];
        const Icon = ICONS[s.key] ?? ShieldAlert;
        const simulated = s.provenance === "simulated";
        return (
          <li
            key={s.key}
            aria-current={s.status === "active" ? "step" : undefined}
            className="relative flex items-start gap-3 rounded-lg border border-transparent px-2 py-2 hover:border-border hover:bg-surface-subtle/60"
          >
            <span
              className={cn(
                "absolute -left-[15px] top-3 flex h-3 w-3 items-center justify-center rounded-full ring-4 ring-surface",
                meta.dot
              )}
            />
            <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", meta.text)} />
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-mono font-semibold uppercase tracking-wider text-fg-secondary">
                  {s.label}
                </span>
                <span
                  className={cn(
                    "shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-mono font-bold uppercase tracking-wider",
                    meta.chip
                  )}
                >
                  {meta.label}
                </span>
              </div>
              <div
                className={cn(
                  "mt-0.5 text-xs font-mono font-medium tabular-nums",
                  meta.text
                )}
              >
                {s.value ?? "—"}
              </div>
              {s.sub && (
                <div className="text-[10px] font-mono text-fg-faint">{s.sub}</div>
              )}
              {(s.provenance || s.note) && (
                <div
                  className={cn(
                    "mt-1 inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] font-mono font-bold uppercase tracking-wider",
                    simulated
                      ? "border-dashed border-status-warning text-status-warning bg-status-warning-bg"
                      : s.provenance === "verified"
                      ? "border-status-success text-status-success bg-status-success-bg"
                      : "border-border text-fg-faint"
                  )}
                >
                  {s.provenance === "simulated" ? (
                    <FlaskConical className="h-2.5 w-2.5" />
                  ) : s.provenance === "verified" ? (
                    <ShieldCheck className="h-2.5 w-2.5" />
                  ) : null}
                  {s.note || (s.provenance === "simulated" ? "Simulated" : "Verified")}
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/* ---------- public component -------------------------------------- */

interface Props {
  stages: PipelineStage[];
  title?: string;
  caption?: string;
  /** Force a single representation regardless of viewport. */
  force?: "timeline";
  className?: string;
}

export function RecoveryPipeline3D({
  stages,
  title = "RECOVERY PIPELINE",
  caption,
  force,
  className,
}: Props) {
  const reduced = usePrefersReducedMotion();
  const timelineOnly = reduced || force === "timeline";

  return (
    <section
      className={cn(
        "rounded-lg border border-border bg-surface/70 backdrop-blur-sm depth-highlight",
        className
      )}
    >
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <h3 className="text-xs font-mono font-semibold uppercase tracking-widest text-fg-secondary">
            {title}
          </h3>
          {caption && (
            <p className="mt-0.5 text-[10px] font-mono text-fg-faint">{caption}</p>
          )}
        </div>
        <span className="hidden sm:inline text-[9px] font-mono uppercase tracking-widest text-fg-faint">
          EVENT → DIAGNOSIS → PREDICTION → STRATEGY → POLICY → ACTION → RAZORPAY → RECOVERED
        </span>
      </div>

      <div className="p-4">
        {timelineOnly ? (
          <TimelineGraph stages={stages} label={title} />
        ) : (
          <>
            {/* mobile */}
            <div className="md:hidden">
              <TimelineGraph stages={stages} label={title} />
            </div>
            {/* tablet — flat compact */}
            <div className="hidden md:block lg:hidden">
              <HorizontalGraph
                stages={stages}
                spatial={false}
                animate={false}
                label={title}
              />
            </div>
            {/* desktop — full spatial */}
            <div className="hidden lg:block">
              <HorizontalGraph
                stages={stages}
                spatial
                animate
                label={title}
              />
            </div>
          </>
        )}
      </div>
    </section>
  );
}
