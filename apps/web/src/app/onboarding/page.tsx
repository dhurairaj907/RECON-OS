"use client";

import React from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { CheckCircle2, Loader2, ArrowRight } from "lucide-react";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { api } from "@/lib/api";
import type { MeResponse } from "@/lib/types";

/**
 * Basic post-registration onboarding — confirms the real organization/role
 * that was just created and hands the operator off to the real Command
 * Center. No invite-teammates flow, no product tour: kept intentionally
 * minimal for this phase.
 */
export default function OnboardingPage() {
  const router = useRouter();
  const { data, error } = useSWR<MeResponse>("/api/v1/auth/me", () => api.me());

  return (
    <AuthLayout title="You're all set" subtitle="Your organization is ready">
      {!data && !error ? (
        <div className="flex items-center justify-center gap-2 py-6 text-sm text-fg-muted">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading your account…
        </div>
      ) : error || !data ? (
        <p className="text-sm text-status-danger">Could not load your account details.</p>
      ) : (
        <div className="space-y-5">
          <div className="flex items-start gap-3 rounded-xl border border-hairline bg-surface-subtle/50 p-4">
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-status-success" />
            <div className="text-sm">
              <p className="font-medium text-fg">{data.organization.name}</p>
              <p className="mt-0.5 text-xs text-fg-muted">
                Signed in as {data.user.email} · Role: {data.role}
              </p>
            </div>
          </div>
          <p className="text-xs leading-relaxed text-fg-muted">
            RECON OS will start observing payment failures the moment they arrive. You can also
            trigger a test event from the Simulator to see the full recovery lifecycle now.
          </p>
          <button
            onClick={() => router.push("/")}
            className="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-accent text-sm font-medium text-white transition-colors hover:bg-accent-hover"
          >
            Go to Command Center <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      )}
    </AuthLayout>
  );
}
