"use client";

import React, { useEffect, useRef } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface DetailDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  badge?: React.ReactNode;
  children: React.ReactNode;
  width?: string;
}

const FOCUSABLE =
  'a[href],button:not([disabled]),textarea,input,select,[tabindex]:not([tabindex="-1"])';

export function DetailDrawer({
  isOpen,
  onClose,
  title,
  subtitle,
  badge,
  children,
  width = "max-w-2xl",
}: DetailDrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);

  // Escape to close + focus trap
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key === "Tab" && panelRef.current) {
        const nodes = Array.from(
          panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)
        ).filter((n) => n.offsetParent !== null);
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
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Scroll lock + focus move/restore
  useEffect(() => {
    if (isOpen) {
      restoreRef.current = document.activeElement as HTMLElement | null;
      document.body.style.overflow = "hidden";
      // move focus into the panel
      const id = window.setTimeout(() => {
        panelRef.current
          ?.querySelector<HTMLElement>(FOCUSABLE)
          ?.focus({ preventScroll: true });
      }, 20);
      return () => window.clearTimeout(id);
    }
    document.body.style.overflow = "unset";
    restoreRef.current?.focus?.({ preventScroll: true });
    return () => {
      document.body.style.overflow = "unset";
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/55 backdrop-blur-md animate-fade-in"
        onClick={onClose}
      />

      {/* Glass panel entering the scene */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          "relative z-10 flex h-full w-full flex-col overflow-hidden border-l border-border-highlight/70",
          "bg-surface/90 backdrop-blur-xl shadow-elevated depth-highlight animate-drawer-in",
          width
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border bg-surface-subtle/70 px-6 py-4 backdrop-blur-sm">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="truncate font-mono text-base font-semibold tracking-wide text-fg">
                {title}
              </h2>
              {badge}
            </div>
            {subtitle && <p className="mt-0.5 text-xs text-fg-muted">{subtitle}</p>}
          </div>
          <button
            onClick={onClose}
            className="flex h-10 w-10 items-center justify-center rounded-md text-fg-muted transition-colors hover:bg-surface-elevated hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            title="Close (Esc)"
            aria-label="Close panel"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 space-y-6 overflow-y-auto p-6">{children}</div>
      </div>
    </div>
  );
}
