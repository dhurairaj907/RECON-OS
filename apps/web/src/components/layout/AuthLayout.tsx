import React from "react";
import Link from "next/link";
import { Layers } from "lucide-react";

/**
 * Minimal centered shell for the auth/account pages (login, register,
 * forgot/reset password, session-expired, onboarding). Deliberately NOT
 * AppShell — those pages have no session yet, so the dashboard-polling
 * TopNav has nothing to show and would just 401-loop. Reuses the same
 * brand mark, tokens, and card language as the rest of RECON OS (no new
 * design system, no new colors).
 */
export function AuthLayout({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="relative flex min-h-screen items-center justify-center bg-background px-4 py-12 text-fg antialiased">
      <div className="w-full max-w-sm space-y-6">
        <Link href="/" className="flex items-center justify-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-accent/40 bg-accent/15 shadow-[0_0_15px_rgb(var(--c-accent)/0.22)]">
            <Layers className="h-4 w-4 text-accent" />
          </div>
          <span className="font-mono text-sm font-bold tracking-widest text-fg">RECON OS</span>
        </Link>

        <div className="rounded-2xl border border-border bg-surface/60 p-6 backdrop-blur-sm sm:p-8">
          <div className="mb-6 text-center">
            <h1 className="text-lg font-semibold text-fg">{title}</h1>
            {subtitle && <p className="mt-1.5 text-sm text-fg-muted">{subtitle}</p>}
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}
