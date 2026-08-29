"use client";

import React, { useState } from "react";
import { Search, Shield, RefreshCw, Terminal, Bell } from "lucide-react";
import { CommandPalette } from "./CommandPalette";

interface HeaderProps {
  onRefresh?: () => void;
  isRefreshing?: boolean;
}

export function Header({ onRefresh, isRefreshing }: HeaderProps) {
  const [paletteOpen, setPaletteOpen] = useState(false);

  return (
    <>
      <header className="h-16 px-6 bg-surface border-b border-border flex items-center justify-between sticky top-0 z-20">
        {/* Left: Search Trigger */}
        <div className="flex items-center space-x-4 flex-1 max-w-md">
          <button
            onClick={() => setPaletteOpen(true)}
            className="w-full flex items-center justify-between px-3.5 py-1.5 rounded-lg bg-surface-subtle border border-border text-xs text-slate-400 hover:border-border-highlight hover:text-slate-300 transition-colors"
          >
            <div className="flex items-center space-x-2">
              <Search className="w-3.5 h-3.5 text-slate-500" />
              <span>Search events, cases, customers...</span>
            </div>
            <kbd className="px-1.5 py-0.5 text-[10px] font-mono text-slate-400 bg-surface-elevated rounded border border-border">
              ⌘K
            </kbd>
          </button>
        </div>

        {/* Right: Operational Controls & Status */}
        <div className="flex items-center space-x-3">
          {onRefresh && (
            <button
              onClick={onRefresh}
              disabled={isRefreshing}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-border bg-surface-subtle text-xs font-mono text-slate-300 hover:text-white hover:bg-surface-elevated transition-colors disabled:opacity-50"
              title="Refresh Data"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin text-accent" : ""}`} />
              <span className="hidden sm:inline">Sync</span>
            </button>
          )}

          {/* System Status Pill */}
          <div className="flex items-center space-x-2 px-3 py-1.5 rounded-lg border border-status-success-border/40 bg-status-success-bg/40 text-xs font-mono text-emerald-400">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
            <span className="hidden sm:inline tracking-wider">SYSTEM OPERATIONAL</span>
          </div>
        </div>
      </header>

      {/* Cmd+K Palette Modal */}
      <CommandPalette isOpen={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </>
  );
}
