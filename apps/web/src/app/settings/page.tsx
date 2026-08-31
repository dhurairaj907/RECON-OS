"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { Building2, LogOut, Mail, Shield, Loader2 } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { SectionBand } from "@/components/modules/SectionBand";
import { FeatureGrid } from "@/components/modules/FeatureGrid";
import { api } from "@/lib/api";
import type { MeResponse } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

export default function SettingsPage() {
  const router = useRouter();
  const { data, error } = useSWR<MeResponse>("/api/v1/auth/me", () => api.me());
  const [loggingOut, setLoggingOut] = useState(false);

  const handleLogout = async () => {
    setLoggingOut(true);
    try {
      await api.logout();
    } finally {
      router.push("/login");
      router.refresh();
    }
  };

  return (
    <AppShell>
      <SectionBand
        eyebrow="ACCOUNT"
        title="SETTINGS"
        subtitle="Your identity, organization, and role within RECON OS."
      />

      {!data && !error ? (
        <p className="text-sm text-fg-muted font-mono">Loading…</p>
      ) : error || !data ? (
        <p className="text-sm text-status-danger font-mono">Could not load account details.</p>
      ) : (
        <>
          <div className="space-y-3">
            <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-fg-secondary">
              Your Account
            </h3>
            <FeatureGrid
              items={[
                { icon: Mail, label: "Email", value: data.user.email },
                { icon: Shield, label: "Role", value: data.role, tone: "info" },
                { icon: Building2, label: "Organization", value: data.organization.name },
                {
                  icon: Mail,
                  label: "Last Login",
                  value: data.user.last_login_at ? formatDateTime(data.user.last_login_at) : "This session",
                },
              ]}
            />
          </div>

          <div className="rounded-2xl border border-hairline bg-surface-subtle/40 p-6">
            <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-fg-secondary">
              Session
            </h3>
            <p className="mt-2 text-xs text-fg-muted">
              Signing out ends this session immediately on the server — the session cookie is
              revoked, not just cleared locally.
            </p>
            <button
              onClick={handleLogout}
              disabled={loggingOut}
              className="mt-4 inline-flex h-10 items-center gap-2 rounded-lg border border-status-danger-border bg-status-danger-bg px-4 text-sm font-medium text-status-danger transition-colors hover:opacity-90 disabled:opacity-50"
            >
              {loggingOut ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogOut className="h-4 w-4" />}
              Sign out
            </button>
          </div>
        </>
      )}
    </AppShell>
  );
}
