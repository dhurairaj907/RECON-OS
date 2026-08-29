"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Search, LayoutDashboard, Zap, ShieldAlert, Users, FlaskConical, ScrollText, ArrowRight, X, BrainCircuit } from "lucide-react";

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
}

export function CommandPalette({ isOpen, onClose }: CommandPaletteProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");

  const navigationItems = [
    { name: "Command Center", href: "/", icon: LayoutDashboard, category: "Navigation" },
    { name: "Live Events Feed", href: "/events", icon: Zap, category: "Navigation" },
    { name: "Recovery Cases", href: "/recovery", icon: ShieldAlert, category: "Navigation" },
    { name: "Intelligence Analyses", href: "/intelligence", icon: BrainCircuit, category: "Navigation" },
    { name: "Customer Intelligence", href: "/customers", icon: Users, category: "Navigation" },
    { name: "Event Simulator Lab", href: "/simulator", icon: FlaskConical, category: "Navigation" },
    { name: "Audit Trail", href: "/audit-logs", icon: ScrollText, category: "Navigation" },
  ];

  const filteredItems = navigationItems.filter((item) =>
    item.name.toLowerCase().includes(query.toLowerCase())
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        onClose(); // toggle logic in parent
      }
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleSelect = (href: string) => {
    router.push(href);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4">
      <div
        className="fixed inset-0 bg-black/70 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />
      <div className="relative z-10 w-full max-w-lg bg-surface border border-border shadow-elevated rounded-xl overflow-hidden animate-fade-in depth-highlight">
        {/* Search Input Bar */}
        <div className="flex items-center px-4 py-3 border-b border-border bg-surface-subtle">
          <Search className="w-4 h-4 text-fg-muted mr-3" />
          <input
            type="text"
            placeholder="Type a command or jump to page..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
            className="flex-1 bg-transparent text-sm text-fg placeholder-fg-faint focus:outline-none"
          />
          <kbd className="hidden sm:inline-block px-1.5 py-0.5 text-[10px] font-mono text-fg-muted bg-surface-elevated rounded border border-border">
            ESC
          </kbd>
        </div>

        {/* List of actions */}
        <div className="max-h-72 overflow-y-auto p-2">
          <div className="text-[11px] font-mono uppercase tracking-wider text-fg-faint px-3 py-1.5">
            Quick Navigation
          </div>
          {filteredItems.length === 0 ? (
            <div className="p-4 text-center text-xs text-fg-muted">No matching commands</div>
          ) : (
            filteredItems.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.href}
                  onClick={() => handleSelect(item.href)}
                  className="w-full flex items-center justify-between px-3 py-2.5 rounded-lg hover:bg-surface-elevated text-fg-secondary hover:text-fg transition-colors text-left text-sm group"
                >
                  <div className="flex items-center space-x-3">
                    <Icon className="w-4 h-4 text-fg-muted group-hover:text-accent transition-colors" />
                    <span>{item.name}</span>
                  </div>
                  <ArrowRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 text-fg-muted transition-opacity" />
                </button>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
