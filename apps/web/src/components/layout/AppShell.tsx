"use client";

import React, { useState } from "react";
import { TopNav } from "./TopNav";
import { MobileNavOverlay } from "./MobileNavOverlay";
import { AmbientBackdrop } from "@/components/spatial/AmbientBackdrop";
import { GrainOverlay } from "@/components/spatial/GrainOverlay";
import { AtmosphericGlow, type GlowTone } from "@/components/spatial/AtmosphericGlow";
import { Reveal } from "@/components/spatial/Reveal";

interface AppShellProps {
  children: React.ReactNode;
  onRefresh?: () => void;
  isRefreshing?: boolean;
  /** Dominant operational state — tints the atmospheric wash. Real-data driven. */
  tone?: GlowTone;
  /** Command Center only — header starts transparent over its hero. */
  transparentHeader?: boolean;
}

/**
 * No permanent sidebar — a floating/sticky top nav (`TopNav`) replaces it,
 * with `MobileNavOverlay` as the off-canvas equivalent below `lg`. The
 * real-data status line that used to live in the sidebar footer now closes
 * every page as a slim, non-marketing footer band.
 */
export function AppShell({
  children,
  onRefresh,
  isRefreshing,
  tone = "idle",
  transparentHeader = false,
}: AppShellProps) {
  const [mobileNav, setMobileNav] = useState(false);

  return (
    <div className="relative min-h-screen text-fg antialiased font-sans">
      <AmbientBackdrop />
      <AtmosphericGlow tone={tone} />
      <GrainOverlay />
      <div className="relative z-10 flex min-h-screen flex-col">
        <TopNav
          onRefresh={onRefresh}
          isRefreshing={isRefreshing}
          onMenuClick={() => setMobileNav(true)}
          transparentOverHero={transparentHeader}
        />
        <main className="mx-auto w-full min-w-0 max-w-7xl flex-1 p-4 sm:p-6 lg:p-8">
          <Reveal className="block space-y-12 sm:space-y-16 lg:space-y-24">{children}</Reveal>
        </main>
        <footer className="border-t border-hairline px-4 py-4 font-mono text-[11px] text-fg-faint sm:px-6 lg:px-8">
          RECON OS · RECON Demo Merchant · Razorpay Integration Active
        </footer>
      </div>
      <MobileNavOverlay isOpen={mobileNav} onClose={() => setMobileNav(false)} />
    </div>
  );
}
