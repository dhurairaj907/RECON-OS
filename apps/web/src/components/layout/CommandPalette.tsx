"use client";

import React, { useState, useEffect, useMemo, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  Search,
  LayoutDashboard,
  Zap,
  ShieldAlert,
  Users,
  FlaskConical,
  ScrollText,
  ArrowRight,
  BrainCircuit,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
}

const NAV_ITEMS = [
  { name: "Command Center", href: "/", icon: LayoutDashboard },
  { name: "Live Events Feed", href: "/events", icon: Zap },
  { name: "Recovery Cases", href: "/recovery", icon: ShieldAlert },
  { name: "Intelligence Analyses", href: "/intelligence", icon: BrainCircuit },
  { name: "Customer Intelligence", href: "/customers", icon: Users },
  { name: "Event Simulator Lab", href: "/simulator", icon: FlaskConical },
  { name: "Audit Trail", href: "/audit-logs", icon: ScrollText },
];

export function CommandPalette({ isOpen, onClose }: CommandPaletteProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(
    () =>
      NAV_ITEMS.filter((item) =>
        item.name.toLowerCase().includes(query.toLowerCase())
      ),
    [query]
  );

  useEffect(() => {
    setActive(0);
  }, [query]);

  useEffect(() => {
    if (!isOpen) {
      setQuery("");
      setActive(0);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive((i) => Math.min(filtered.length - 1, i + 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive((i) => Math.max(0, i - 1));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const target = filtered[active];
        if (target) handleSelect(target.href);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, filtered, active, onClose]);

  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLElement>(`[data-idx="${active}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [active]);

  if (!isOpen) return null;

  const handleSelect = (href: string) => {
    router.push(href);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-24">
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-md"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="animate-drawer-in depth-highlight relative z-10 w-full max-w-lg overflow-hidden rounded-2xl border border-border-highlight/70 bg-surface/90 shadow-elevated backdrop-blur-xl"
      >
        <div className="flex h-14 items-center border-b border-border bg-surface-subtle/70 px-4">
          <Search className="mr-3 h-4 w-4 text-fg-muted" />
          <input
            type="text"
            placeholder="Type a command or jump to page..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
            role="combobox"
            aria-expanded="true"
            aria-controls="cmdk-list"
            aria-activedescendant={filtered[active] ? `cmdk-opt-${active}` : undefined}
            className="flex-1 bg-transparent text-base text-fg placeholder-fg-faint focus:outline-none"
          />
          <kbd className="hidden rounded border border-border bg-surface-elevated px-1.5 py-0.5 font-mono text-[11px] text-fg-muted sm:inline-block">
            ESC
          </kbd>
        </div>

        <div id="cmdk-list" ref={listRef} className="max-h-72 overflow-y-auto p-2">
          <div className="px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider text-fg-faint">
            Quick Navigation
          </div>
          {filtered.length === 0 ? (
            <div className="p-4 text-center text-xs text-fg-muted">
              No matching commands
            </div>
          ) : (
            filtered.map((item, idx) => {
              const Icon = item.icon;
              const isActive = idx === active;
              return (
                <button
                  key={item.href}
                  id={`cmdk-opt-${idx}`}
                  data-idx={idx}
                  role="option"
                  aria-selected={isActive}
                  onMouseMove={() => setActive(idx)}
                  onClick={() => handleSelect(item.href)}
                  className={cn(
                    "group flex w-full items-center justify-between rounded-lg px-3.5 py-3 text-left text-sm transition-colors",
                    isActive
                      ? "bg-surface-elevated text-fg"
                      : "text-fg-secondary hover:text-fg"
                  )}
                >
                  <div className="flex items-center space-x-3">
                    <Icon
                      className={cn(
                        "h-4 w-4 transition-colors",
                        isActive ? "text-accent" : "text-fg-muted"
                      )}
                    />
                    <span>{item.name}</span>
                  </div>
                  <ArrowRight
                    className={cn(
                      "h-3.5 w-3.5 text-fg-muted transition-opacity",
                      isActive ? "opacity-100" : "opacity-0"
                    )}
                  />
                </button>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
