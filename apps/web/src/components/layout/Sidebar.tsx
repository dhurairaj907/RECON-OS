"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Zap,
  ShieldAlert,
  Users,
  FlaskConical,
  ScrollText,
  Layers,
  BrainCircuit,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navigationItems = [
  { name: "Command Center", href: "/", icon: LayoutDashboard },
  { name: "Live Events", href: "/events", icon: Zap },
  { name: "Recovery Cases", href: "/recovery", icon: ShieldAlert },
  { name: "Intelligence", href: "/intelligence", icon: BrainCircuit },
  { name: "Customers", href: "/customers", icon: Users },
  { name: "Simulator", href: "/simulator", icon: FlaskConical },
  { name: "Audit Trail", href: "/audit-logs", icon: ScrollText },
];

const COLLAPSE_KEY = "recon-sidebar-collapsed";

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    try {
      setCollapsed(localStorage.getItem(COLLAPSE_KEY) === "1");
    } catch {
      /* ignore */
    }
  }, []);

  const toggle = () =>
    setCollapsed((c) => {
      const next = !c;
      try {
        localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });

  // ⌘\ / Ctrl+\ toggles the rail
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "\\") {
        e.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <aside
      className={cn(
        "relative bg-surface border-r border-border flex flex-col justify-between h-screen sticky top-0 shrink-0 z-30 select-none transition-[width] duration-300 ease-spatial",
        collapsed ? "w-[68px]" : "w-64"
      )}
    >
      {/* hairline accent bar — instant "product" signal */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-accent/0 via-accent/60 to-accent/0" />

      <div>
        {/* Brand */}
        <div
          className={cn(
            "h-16 flex items-center border-b border-border",
            collapsed ? "justify-center px-0" : "px-6 gap-3"
          )}
        >
          <div className="w-8 h-8 shrink-0 rounded-lg bg-accent/15 border border-accent/40 flex items-center justify-center shadow-[0_0_15px_rgb(var(--c-accent)/0.22)]">
            <Layers className="w-4 h-4 text-accent" />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <div className="font-mono font-bold text-sm text-fg tracking-widest flex items-center gap-1.5">
                RECON OS
                <span className="text-[10px] px-1 py-0.5 rounded bg-accent/20 text-accent font-normal">
                  v1.0
                </span>
              </div>
              <p className="text-[10px] font-mono text-fg-muted tracking-tight">
                Revenue Recovery Engine
              </p>
            </div>
          )}
        </div>

        {/* Navigation */}
        <nav className={cn("py-3 space-y-1", collapsed ? "px-2" : "px-3")}>
          {!collapsed && (
            <div className="text-[10px] font-mono uppercase tracking-widest text-fg-faint px-3 py-2">
              Operations
            </div>
          )}
          {navigationItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                title={collapsed ? item.name : undefined}
                aria-current={isActive ? "page" : undefined}
                className={cn(
                  "group relative flex items-center rounded-lg text-xs font-medium transition-colors duration-150",
                  collapsed ? "justify-center h-9 w-9 mx-auto" : "gap-3 px-3 py-2",
                  isActive
                    ? "bg-accent/10 text-fg font-semibold"
                    : "text-fg-muted hover:text-fg hover:bg-surface-elevated"
                )}
              >
                {/* left-border active indicator */}
                <span
                  className={cn(
                    "absolute left-0 top-1/2 -translate-y-1/2 h-5 w-0.5 rounded-r bg-accent transition-opacity",
                    isActive ? "opacity-100" : "opacity-0"
                  )}
                />
                <Icon
                  className={cn(
                    "w-4 h-4 shrink-0 transition-colors",
                    isActive ? "text-accent" : "text-fg-muted group-hover:text-fg"
                  )}
                />
                {!collapsed && <span className="truncate">{item.name}</span>}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Footer / System Status */}
      <div className="border-t border-border bg-surface-subtle">
        <button
          type="button"
          onClick={toggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={`${collapsed ? "Expand" : "Collapse"} sidebar  (⌘\\)`}
          className={cn(
            "w-full flex items-center gap-2 px-4 py-2.5 text-[11px] font-mono text-fg-muted hover:text-fg hover:bg-surface-hover transition-colors",
            collapsed && "justify-center px-0"
          )}
        >
          {collapsed ? (
            <PanelLeftOpen className="w-4 h-4" />
          ) : (
            <>
              <PanelLeftClose className="w-4 h-4" />
              <span>Collapse</span>
            </>
          )}
        </button>

        {!collapsed && (
          <div className="p-4 pt-2 border-t border-border/60">
            <div className="flex items-center justify-between text-[11px] font-mono text-fg-muted">
              <div className="flex items-center space-x-2">
                <span className="relative flex h-2 w-2">
                  <span className="motion-safe-only animate-ping absolute inline-flex h-full w-full rounded-full bg-status-success opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-status-success" />
                </span>
                <span className="text-fg-secondary font-medium">PHASE 2 (THINK)</span>
              </div>
              <span className="text-fg-faint">TEST MODE</span>
            </div>
            <div className="mt-2 text-[10px] text-fg-faint">
              Razorpay Integration Active
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
