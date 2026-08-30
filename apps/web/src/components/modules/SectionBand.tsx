import React from "react";
import { cn } from "@/lib/utils";

interface SectionBandProps {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  className?: string;
}

/**
 * Compact page-identity band for the 6 non-Command-Center routes — the
 * reference's "wavy light-streak" section-title motif, reinterpreted:
 * dark mode gets a faint radial light wash (echoing AmbientBackdrop's own
 * light-cone technique); light mode drops the glow entirely for a flat
 * surface + hairline borders, per the brief's "different treatment, not an
 * inversion" instruction for cinematic/glowing surfaces.
 */
export function SectionBand({ eyebrow, title, subtitle, className }: SectionBandProps) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-2xl border border-hairline bg-surface-subtle/60 px-6 py-10 text-center sm:py-14",
        className
      )}
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 hidden dark:block"
        style={{
          background:
            "radial-gradient(900px 420px at 50% -30%, var(--ambient-1), transparent 70%)",
        }}
      />
      <div className="relative">
        {eyebrow && <div className="label-mono">{eyebrow}</div>}
        <h1 className={cn("display-lg font-bold text-fg", eyebrow ? "mt-2" : "")}>{title}</h1>
        {subtitle && (
          <p className="mx-auto mt-3 max-w-xl text-xs text-fg-muted">{subtitle}</p>
        )}
      </div>
    </div>
  );
}
