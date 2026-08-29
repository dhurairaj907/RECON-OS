import React from "react";

export type ConnectorState = "done" | "active" | "pending" | "halt";

interface FlowConnectorProps {
  /** Coordinates in the parent SVG's user space. */
  x1: number;
  x2: number;
  y: number;
  state: ConnectorState;
  /** Enable the crawling dash + travelling pulse (desktop, motion-safe only). */
  animate?: boolean;
  id: string;
}

/**
 * One segment of the pipeline flow, as inline SVG.
 *
 *   done    → solid connected line
 *   active  → animated dashed path + a small travelling pulse
 *   pending → static dim line
 *   halt    → dim warning-tinted line (flow stopped here)
 *
 * Motion is opt-in via `animate`; callers pass it only on desktop when
 * reduced-motion is not set.
 */
export function FlowConnector({
  x1,
  x2,
  y,
  state,
  animate = false,
  id,
}: FlowConnectorProps) {
  const stroke =
    state === "done"
      ? "rgb(var(--c-success))"
      : state === "active"
      ? "rgb(var(--c-accent))"
      : state === "halt"
      ? "rgb(var(--c-warning))"
      : "rgb(var(--c-border-highlight))";

  const opacity = state === "pending" ? 0.5 : state === "halt" ? 0.6 : 0.9;

  return (
    <g aria-hidden="true">
      {/* base rail */}
      <line
        x1={x1}
        y1={y}
        x2={x2}
        y2={y}
        stroke="rgb(var(--c-border-highlight))"
        strokeWidth={1.5}
        strokeOpacity={0.4}
      />
      <line
        x1={x1}
        y1={y}
        x2={x2}
        y2={y}
        stroke={stroke}
        strokeOpacity={opacity}
        strokeWidth={state === "done" ? 2 : 1.75}
        strokeLinecap="round"
        strokeDasharray={state === "active" ? "5 5" : undefined}
        className={
          state === "active" && animate ? "animate-flow-dash" : undefined
        }
      />
      {state === "active" && animate && (
        <circle r={2.4} fill="rgb(var(--c-accent))">
          <animateMotion
            dur="1.6s"
            repeatCount="indefinite"
            path={`M ${x1} ${y} L ${x2} ${y}`}
          />
        </circle>
      )}
      <title>{`${id} connector — ${state}`}</title>
    </g>
  );
}
