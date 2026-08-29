"use client";

import React from "react";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
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
}

export function AppShell({ children, onRefresh, isRefreshing, tone = "idle" }: AppShellProps) {
  return (
    <div className="relative min-h-screen text-fg antialiased font-sans">
      <AmbientBackdrop />
      <AtmosphericGlow tone={tone} />
      <GrainOverlay />
      <div className="relative z-10 flex min-h-screen">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <Header onRefresh={onRefresh} isRefreshing={isRefreshing} />
          <main className="flex-1 p-6 lg:p-8 max-w-7xl w-full mx-auto">
            <Reveal className="space-y-6 block">{children}</Reveal>
          </main>
        </div>
      </div>
    </div>
  );
}
