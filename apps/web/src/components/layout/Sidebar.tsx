"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Zap,
  ShieldAlert,
  Users,
  FlaskConical,
  ScrollText,
  Activity,
  Layers,
  BrainCircuit,
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

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 bg-surface border-r border-border flex flex-col justify-between h-screen sticky top-0 shrink-0 z-30 select-none">
      {/* Brand & Identity */}
      <div>
        <div className="h-16 px-6 flex items-center space-x-3 border-b border-border">
          {/* RECON OS Geometric Mark */}
          <div className="w-8 h-8 rounded-lg bg-accent/20 border border-accent/40 flex items-center justify-center text-accent font-mono font-bold text-sm shadow-[0_0_15px_rgba(37,99,235,0.25)]">
            <Layers className="w-4 h-4 text-blue-400" />
          </div>
          <div>
            <div className="font-mono font-bold text-sm text-white tracking-widest flex items-center gap-1.5">
              RECON OS
              <span className="text-[10px] px-1 py-0.2 rounded bg-accent/30 text-blue-300 font-normal">v1.0</span>
            </div>
            <p className="text-[10px] font-mono text-slate-400 tracking-tight">Revenue Recovery Engine</p>
          </div>
        </div>

        {/* Navigation Section */}
        <nav className="p-3 space-y-1">
          <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 px-3 py-2">
            Operations
          </div>
          {navigationItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center space-x-3 px-3 py-2 rounded-lg text-xs font-medium transition-all duration-150 group",
                  isActive
                    ? "bg-accent text-white shadow-sm font-semibold"
                    : "text-slate-400 hover:text-white hover:bg-surface-elevated"
                )}
              >
                <Icon
                  className={cn(
                    "w-4 h-4 transition-colors",
                    isActive ? "text-white" : "text-slate-400 group-hover:text-white"
                  )}
                />
                <span>{item.name}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Footer / System Status */}
      <div className="p-4 border-t border-border bg-surface-subtle">
        <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
          <div className="flex items-center space-x-2">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span className="text-slate-300 font-medium">PHASE 2 (THINK)</span>
          </div>
          <span className="text-slate-500">TEST MODE</span>
        </div>
        <div className="mt-2 text-[10px] text-slate-500">
          Razorpay Integration Active
        </div>
      </div>
    </aside>
  );
}
