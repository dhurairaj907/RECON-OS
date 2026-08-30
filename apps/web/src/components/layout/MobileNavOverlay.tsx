"use client";

import React, { useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  X,
  LayoutDashboard,
  Zap,
  ShieldAlert,
  BrainCircuit,
  ClipboardCheck,
  Users,
  BarChart3,
  Scale,
  FlaskConical,
  ScrollText,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { name: "Command Center", href: "/", icon: LayoutDashboard },
  { name: "Live Events", href: "/events", icon: Zap },
  { name: "Recovery", href: "/recovery", icon: ShieldAlert },
  { name: "Intelligence", href: "/intelligence", icon: BrainCircuit },
  { name: "Approvals", href: "/approvals", icon: ClipboardCheck },
  { name: "Customers", href: "/customers", icon: Users },
  { name: "Analytics", href: "/analytics", icon: BarChart3 },
  { name: "Policies", href: "/policies", icon: Scale },
  { name: "Simulator", href: "/simulator", icon: FlaskConical },
  { name: "Audit Trail", href: "/audit-logs", icon: ScrollText },
];

interface MobileNavOverlayProps {
  isOpen: boolean;
  onClose: () => void;
}

const FOCUSABLE = 'a[href],button:not([disabled]),[tabindex]:not([tabindex="-1"])';

/**
 * Full-screen tap-friendly navigation sheet — deliberately separate from
 * CommandPalette. This is for browsing (large targets, glanceable state);
 * the palette stays the fast fuzzy-jump/⌘K tool. Reuses DetailDrawer's
 * animate-drawer-in + focus-trap pattern.
 */
export function MobileNavOverlay({ isOpen, onClose }: MobileNavOverlayProps) {
  const pathname = usePathname();
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    onClose();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key === "Tab" && panelRef.current) {
        const nodes = Array.from(panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
          (n) => n.offsetParent !== null
        );
        if (nodes.length === 0) return;
        const first = nodes[0];
        const last = nodes[nodes.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    document.body.style.overflow = "hidden";
    const id = window.setTimeout(() => {
      panelRef.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus({ preventScroll: true });
    }, 20);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "unset";
      window.clearTimeout(id);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-md" onClick={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Navigation"
        className="animate-drawer-in relative z-10 flex h-full w-full flex-col bg-surface/95 backdrop-blur-xl"
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <span className="font-mono text-sm font-bold tracking-widest text-fg">RECON OS</span>
          <button
            onClick={onClose}
            aria-label="Close navigation"
            className="flex h-10 w-10 items-center justify-center rounded-md text-fg-muted transition-colors hover:bg-surface-elevated hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <nav className="flex-1 space-y-1 overflow-y-auto p-4">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive ? "page" : undefined}
                className={cn(
                  "flex items-center gap-3 rounded-xl px-4 py-3.5 text-base font-medium transition-colors",
                  isActive
                    ? "bg-accent/10 font-semibold text-fg"
                    : "text-fg-secondary hover:bg-surface-elevated"
                )}
              >
                <Icon className={cn("h-5 w-5", isActive ? "text-accent" : "text-fg-muted")} />
                {item.name}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-border p-4 font-mono text-xs text-fg-muted">
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-status-success" />
            <span className="font-medium text-fg-secondary">PHASE 4 (PROVE)</span>
          </div>
          <div className="mt-1">Razorpay Integration Active</div>
        </div>
      </div>
    </div>
  );
}
