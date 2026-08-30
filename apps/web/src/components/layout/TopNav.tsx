"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import useSWR from "swr";
import { Layers, Search, Menu, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { DashboardMetrics } from "@/lib/types";
import { ThemeToggle } from "./ThemeToggle";
import { CommandPalette } from "./CommandPalette";

const NAV_ITEMS = [
  { name: "Command Center", href: "/" },
  { name: "Live Events", href: "/events" },
  { name: "Recovery", href: "/recovery" },
  { name: "Intelligence", href: "/intelligence" },
  { name: "Approvals", href: "/approvals" },
  { name: "Customers", href: "/customers" },
  { name: "Analytics", href: "/analytics" },
  { name: "Policies", href: "/policies" },
  { name: "Simulator", href: "/simulator" },
  { name: "Audit Trail", href: "/audit-logs" },
] as const;

/** Routes that carry a real-data attention dot. Every value below is derived
 * from the same DashboardMetrics payload every list page already polls —
 * no new endpoint, no fabricated state. */
const STATUS_ROUTES = ["/events", "/recovery", "/approvals"] as const;

interface TopNavProps {
  onRefresh?: () => void;
  isRefreshing?: boolean;
  onMenuClick: () => void;
  /** Command Center only — starts transparent over its hero, gains the
   * glass surface once scrolled past it. */
  transparentOverHero?: boolean;
}

export function TopNav({ onRefresh, isRefreshing, onMenuClick, transparentOverHero = false }: TopNavProps) {
  const pathname = usePathname();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [scrolled, setScrolled] = useState(!transparentOverHero);

  // Shared SWR key — dedupes against whatever the page itself already
  // fetches; this adds a poll only on the 4 routes that don't already fetch
  // dashboard metrics (Events/Customers/Simulator/Audit), purely to power
  // the real-data nav indicators below.
  const { data: metrics } = useSWR<DashboardMetrics>(
    "/api/v1/dashboard/metrics",
    () => api.getDashboardMetrics(),
    { refreshInterval: 5000 }
  );

  useEffect(() => {
    if (!transparentOverHero) {
      setScrolled(true);
      return;
    }
    const onScroll = () => setScrolled(window.scrollY > window.innerHeight * 0.6);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [transparentOverHero]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const criticalCases = (metrics?.recent_cases || []).filter(
    (c) => c.priority === "CRITICAL" && (c.status || "").toUpperCase() !== "RESOLVED"
  ).length;
  const anyActiveCase = (metrics?.recent_cases || []).some(
    (c) => (c.status || "").toUpperCase() !== "RESOLVED" && (c.status || "").toUpperCase() !== "CLOSED"
  );
  const needsApproval = metrics?.intelligence?.needs_approval ?? 0;

  const dotFor: Record<(typeof STATUS_ROUTES)[number], { show: boolean; tone: string; pulse?: boolean } | undefined> = {
    "/events": metrics ? { show: (metrics.events_processed ?? 0) > 0, tone: "bg-status-info", pulse: true } : undefined,
    "/recovery": metrics
      ? { show: anyActiveCase, tone: criticalCases >= 3 ? "bg-status-danger" : criticalCases > 0 ? "bg-status-warning" : "bg-status-info" }
      : undefined,
    "/approvals": metrics ? { show: needsApproval > 0, tone: "bg-status-warning" } : undefined,
  };

  const testMode = metrics?.actions?.test_mode;

  return (
    <>
      <header
        className={cn(
          "sticky top-0 z-30 flex h-[72px] items-center gap-2 px-4 transition-[background-color,border-color,backdrop-filter] duration-300 sm:px-6",
          scrolled
            ? "depth-highlight border-b border-border/80 bg-surface/75 backdrop-blur-xl"
            : "border-b border-transparent bg-transparent"
        )}
      >
        <button
          onClick={onMenuClick}
          aria-label="Open navigation"
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border bg-surface-subtle text-fg-muted transition-colors hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent lg:hidden"
        >
          <Menu className="h-5 w-5" />
        </button>

        <Link href="/" className="flex shrink-0 items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-accent/40 bg-accent/15 shadow-[0_0_15px_rgb(var(--c-accent)/0.22)]">
            <Layers className="h-4 w-4 text-accent" />
          </div>
          <span className="hidden font-mono text-sm font-bold tracking-widest text-fg sm:inline">
            RECON OS
          </span>
        </Link>

        <nav className="no-scrollbar hidden min-w-0 flex-1 items-center gap-0.5 overflow-x-auto lg:flex xl:justify-center xl:gap-1">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href;
            const dot = (dotFor as Record<string, { show: boolean; tone: string; pulse?: boolean } | undefined>)[item.href];
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive ? "page" : undefined}
                className={cn(
                  "relative flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-2 text-sm font-medium transition-colors xl:px-3",
                  isActive ? "bg-accent/10 font-semibold text-fg" : "text-fg-muted hover:text-fg"
                )}
              >
                {item.name}
                {dot?.show && (
                  <span
                    className={cn(
                      "h-1.5 w-1.5 rounded-full",
                      dot.tone,
                      dot.pulse && "motion-safe-only animate-pulse"
                    )}
                  />
                )}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex shrink-0 items-center gap-2 sm:gap-2.5">
          <button
            onClick={() => setPaletteOpen(true)}
            className="hidden h-10 items-center gap-2 rounded-lg border border-border bg-surface-subtle px-4 text-sm text-fg-muted transition-colors hover:border-border-highlight hover:text-fg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent 2xl:flex"
          >
            <Search className="h-4 w-4" />
            <span>Search</span>
            <kbd className="ml-1 rounded border border-border bg-surface-elevated px-1.5 py-0.5 font-mono text-[11px] text-fg-muted">
              ⌘K
            </kbd>
          </button>
          <button
            onClick={() => setPaletteOpen(true)}
            aria-label="Search"
            className="flex h-10 w-10 items-center justify-center rounded-lg border border-border bg-surface-subtle text-fg-muted 2xl:hidden"
          >
            <Search className="h-4 w-4" />
          </button>

          {onRefresh && (
            <button
              onClick={onRefresh}
              disabled={isRefreshing}
              title="Refresh Data"
              className="hidden h-10 items-center gap-1.5 rounded-lg border border-border bg-surface-subtle px-3.5 font-mono text-sm text-fg-secondary transition-colors hover:bg-surface-elevated hover:text-fg disabled:opacity-50 sm:flex"
            >
              <RefreshCw className={cn("h-4 w-4", isRefreshing && "animate-spin text-accent")} />
            </button>
          )}

          <div
            className="hidden h-10 items-center gap-1.5 rounded-lg border border-border bg-surface-subtle px-3.5 md:flex"
            title="System status — Events / Recovery / Approvals"
          >
            {STATUS_ROUTES.map((route) => {
              const d = dotFor[route];
              return (
                <span
                  key={route}
                  className={cn("h-1.5 w-1.5 rounded-full", d?.show ? d.tone : "bg-fg-faint/40")}
                />
              );
            })}
          </div>

          <ThemeToggle />

          {metrics?.merchant_name && (
            <div className="hidden h-10 items-center gap-1.5 rounded-lg border border-border bg-surface-subtle px-3.5 font-mono text-xs text-fg-muted 2xl:flex">
              <span className="truncate">{metrics.merchant_name}</span>
              {testMode && <span className="text-status-warning">· TEST MODE</span>}
            </div>
          )}
        </div>
      </header>

      <CommandPalette isOpen={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </>
  );
}
