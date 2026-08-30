"use client";

import React from "react";
import { cn } from "@/lib/utils";
import { usePointerParallax } from "@/hooks/usePointerParallax";

type GlowTone = "info" | "success" | "warning" | "danger";

interface DepthCardProps extends React.HTMLAttributes<HTMLDivElement> {
  as?: keyof JSX.IntrinsicElements;
  /** Add the hover lift + accent-ring interaction (for clickable / live cards). */
  interactive?: boolean;
  /** Add the 1px top light highlight so it reads as a raised plane. */
  highlight?: boolean;
  /** Elevation baseline. */
  elevation?: "flat" | "card" | "raised";
  /** State-tinted outer glow (dark mode only — a no-op class in light). */
  glow?: GlowTone;
  /** Subtle cursor-follow tilt. Auto-disabled on touch / reduced-motion. */
  tilt?: boolean;
  children: React.ReactNode;
}

/**
 * The RECON depth primitive. Subtle by design:
 *   - token border + restrained shadow
 *   - optional 1px top highlight
 *   - optional hover: -1px lift + accent ring
 *   - optional state glow / cursor tilt
 *
 * Works in both themes (all values are semantic tokens). No big floating shadows.
 */
export function DepthCard({
  as = "div",
  interactive = false,
  highlight = false,
  elevation = "card",
  glow,
  tilt = false,
  className,
  style,
  children,
  ...rest
}: DepthCardProps) {
  const Tag = as as any;
  const tiltRef = usePointerParallax<HTMLDivElement>({ disabled: !tilt, max: 2.5 });

  return (
    <Tag
      ref={tilt ? (tiltRef as any) : undefined}
      style={
        tilt
          ? {
              ...style,
              transform:
                "perspective(900px) rotateX(var(--rx,0deg)) rotateY(var(--ry,0deg))",
            }
          : style
      }
      className={cn(
        "relative rounded-xl border border-border bg-surface transition-all duration-150 ease-spatial",
        elevation === "card" && "shadow-card",
        elevation === "raised" && "shadow-elevated",
        highlight && "depth-highlight",
        glow === "info" && "glow-info",
        glow === "success" && "glow-success",
        glow === "warning" && "glow-warning",
        glow === "danger" && "glow-danger",
        interactive &&
          "hover:-translate-y-px hover:border-accent/30 hover:shadow-depth-hover",
        tilt && "will-change-transform",
        className
      )}
      {...rest}
    >
      {children}
    </Tag>
  );
}
