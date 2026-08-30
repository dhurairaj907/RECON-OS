"use client";

import React from "react";
import Link from "next/link";
import { ArrowUpRight, TrendingDown } from "lucide-react";
import { cn, formatINR } from "@/lib/utils";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
import { AmbientVideo } from "@/components/spatial/AmbientVideo";
import { useTheme } from "@/lib/theme";
import type { DashboardMetrics } from "@/lib/types";
import type { GlowTone } from "@/components/spatial/AtmosphericGlow";

const toneText: Record<GlowTone, string> = {
  idle: "text-fg-faint",
  info: "text-status-info",
  success: "text-status-success",
  warning: "text-status-warning",
  danger: "text-status-danger",
};

/**
 * Command Center hero — a single cinematic banner. The operational content
 * (status line, live revenue figure, simulator entry) is unchanged; the WebGL
 * recovery field (passed in as `scene`) bleeds off the right edge behind a
 * left-to-right scrim so the numbers stay perfectly legible. Every figure is a
 * real backend metric; `AnimatedNumber` only tweens on a real change.
 */
export function CommandCenterHero({
  metrics,
  tone,
  scene,
}: {
  metrics: DashboardMetrics | undefined;
  tone: GlowTone;
  scene?: React.ReactNode;
}) {
  const secured = metrics?.revenue_secured ?? "0";
  const atRisk = metrics?.revenue_at_risk ?? "0";
  const activeCases = metrics?.active_recovery_cases ?? 0;
  const { effective } = useTheme();

  return (
    <section className="relative overflow-hidden rounded-2xl border border-border bg-surface/40 depth-highlight backdrop-blur-sm">
      {/* edge-bleed visual — WebGL + video in dark mode only; a heavily
          filtered video or a matte-black WebGL core on an off-white page
          reads as a rendering bug, not restraint. Light mode gets a soft
          gradient instead. */}
      {scene ? (
        <div className="pointer-events-none absolute inset-y-0 right-0 hidden w-[70%] lg:block">
          {effective === "dark" ? (
            <>
              <AmbientVideo />
              {scene}
            </>
          ) : (
            <div
              aria-hidden="true"
              className="absolute inset-0"
              style={{
                background:
                  "radial-gradient(900px 600px at 70% 30%, var(--ambient-1), transparent 65%), radial-gradient(700px 500px at 90% 80%, var(--ambient-2), transparent 60%)",
              }}
            />
          )}
          {/* scrim: opaque at the text edge, clears quickly over the field */}
          <div
            className="absolute inset-0"
            style={{
              background:
                "linear-gradient(to right, rgb(var(--c-surface)) 0%, rgb(var(--c-surface) / 0.55) 16%, rgb(var(--c-surface) / 0) 46%)",
            }}
          />
        </div>
      ) : null}

      <div className="relative p-6 sm:p-8 lg:max-w-[52%] lg:py-10">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "motion-safe-only h-2 w-2 animate-pulse rounded-full bg-current",
                toneText[tone]
              )}
            />
            <span className="label-mono">Financial Control System</span>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/recovery"
              className="hidden h-10 items-center gap-2 rounded-lg border border-border bg-surface-subtle px-4 font-mono text-sm font-medium text-fg-secondary transition-colors hover:border-border-highlight hover:text-fg sm:inline-flex"
            >
              <span>View Recovery Cases</span>
            </Link>
            <Link
              href="/simulator"
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-accent px-4 font-mono text-sm font-medium text-white shadow-sm transition-colors hover:bg-accent-hover"
            >
              <span>Open Event Simulator</span>
              <ArrowUpRight className="h-4 w-4" />
            </Link>
          </div>
        </div>

        <h1 className="display-lg mt-5 font-bold text-fg">REVENUE RECOVERY CONTROL</h1>

        <div className="mt-7">
          <div className="label-mono">Revenue Secured · lifetime</div>
          <AnimatedNumber
            as="div"
            value={secured}
            format={(n) => formatINR(n)}
            className="display-xl mt-1.5 font-bold text-status-success"
          />
          <p className="mt-3 max-w-md text-sm leading-relaxed text-fg-muted">
            Real-time detection, observation and lifecycle monitoring for Razorpay
            payment infrastructure.
          </p>
        </div>

        <div className="mt-7 flex flex-wrap gap-x-10 gap-y-4 border-t border-hairline pt-5">
          <div>
            <div className="flex items-center gap-1.5">
              <TrendingDown className="h-3 w-3 text-status-danger" />
              <span className="label-mono">Revenue at Risk</span>
            </div>
            <AnimatedNumber
              as="div"
              value={atRisk}
              format={(n) => formatINR(n)}
              className="mt-1.5 text-2xl font-bold tracking-tight text-status-danger tabular-nums lg:text-[1.7rem]"
            />
          </div>
          <div>
            <span className="label-mono">Active Cases</span>
            <AnimatedNumber
              as="div"
              value={activeCases}
              className="mt-1.5 text-2xl font-bold tracking-tight text-fg tabular-nums lg:text-[1.7rem]"
            />
          </div>
        </div>
      </div>
    </section>
  );
}
