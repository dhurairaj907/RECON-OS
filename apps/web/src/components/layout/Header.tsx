"use client";

import React, { useState } from "react";
import { Search, RefreshCw } from "lucide-react";
import { CommandPalette } from "./CommandPalette";
import { ThemeToggle } from "./ThemeToggle";

interface HeaderProps {
  onRefresh?: () => void;
  isRefreshing?: boolean;
}

export function Header({ onRefresh, isRefreshing }: HeaderProps) {
  const [paletteOpen, setPaletteOpen] = useState(false);

  return (
    <>
      <header className="depth-highlight h-16 px-6 bg-surface/85 backdrop-blur-md border-b border-border flex items-center justify-between sticky top-0 z-20">
        {/* Left: Search Trigger */}
        <div className="flex items-center space-x-4 flex-1 max-w-md">
          <button
            onClick={() => setPaletteOpen(true)}
            className="w-full flex items-center justify-between px-3.5 py-1.5 rounded-lg bg-surface-subtle border border-border text-xs text-fg-muted hover:border-border-highlight hover:text-fg-secondary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <div className="flex items-center space-x-2">
              <Search className="w-3.5 h-3.5 text-fg-faint" />
              <span>Search events, cases, customers...</span>
            </div>
            <kbd className="px-1.5 py-0.5 text-[10px] font-mono text-fg-muted bg-surface-elevated rounded border border-border">
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
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-border bg-surface-subtle text-xs font-mono text-fg-secondary hover:text-fg hover:bg-surface-elevated transition-colors disabled:opacity-50 active:scale-[0.97] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              title="Refresh Data"
            >
              <RefreshCw
                className={`w-3.5 h-3.5 ${
                  isRefreshing ? "animate-spin text-accent" : ""
                }`}
              />
              <span className="hidden sm:inline">Sync</span>
            </button>
          )}

          <ThemeToggle />

          {/* System Status Pill */}
          <div className="flex items-center space-x-2 px-3 py-1.5 rounded-lg border border-status-success-border/40 bg-status-success-bg/40 text-xs font-mono text-status-success">
            <span className="w-1.5 h-1.5 rounded-full bg-status-success" />
            <span className="hidden sm:inline tracking-wider">
              SYSTEM OPERATIONAL
            </span>
          </div>
        </div>
      </header>

      <CommandPalette
        isOpen={paletteOpen}
        onClose={() => setPaletteOpen(false)}
      />
    </>
  );
}
