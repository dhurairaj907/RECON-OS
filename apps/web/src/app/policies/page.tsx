"use client";

import React from "react";
import useSWR from "swr";
import { Scale, Ban, AlertTriangle, Info, ShieldCheck } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { SectionBand } from "@/components/modules/SectionBand";
import { FeatureGrid } from "@/components/modules/FeatureGrid";
import { SkeletonRow } from "@/components/ui/SkeletonLoader";
import { api } from "@/lib/api";
import { PolicyOverview } from "@/lib/types";
import { cn, formatINR } from "@/lib/utils";

const decisionTone: Record<string, { tone: "danger" | "warning" | "info"; icon: typeof Ban }> = {
  REJECTED: { tone: "danger", icon: Ban },
  NEEDS_APPROVAL: { tone: "warning", icon: AlertTriangle },
  Informational: { tone: "info", icon: Info },
};

function toneFor(decision: string) {
  if (decision.startsWith("REJECTED")) return decisionTone.REJECTED;
  if (decision.startsWith("NEEDS_APPROVAL")) return decisionTone.NEEDS_APPROVAL;
  return decisionTone.Informational;
}

const toneClasses: Record<string, string> = {
  danger: "border-status-danger-border bg-status-danger-bg text-status-danger",
  warning: "border-status-warning-border bg-status-warning-bg text-status-warning",
  info: "border-status-info-border bg-status-info-bg text-status-info",
};

/**
 * Read-only operational view of the ONE real Policy Engine
 * (services/intelligence/policy_engine.py) — every threshold and rule
 * description below is generated server-side from live `config.settings`,
 * not duplicated here. See routers/policies.py for why this stays read-only.
 */
export default function PoliciesPage() {
  const { data, error } = useSWR<PolicyOverview>("/api/v1/policies", () => api.getPolicies());
  const isLoading = !data && !error;

  return (
    <AppShell>
      <SectionBand
        eyebrow="DETERMINISTIC POLICY ENGINE"
        title="POLICIES"
        subtitle="Every recovery action is gated by these deterministic rules before it ever reaches Razorpay — no LLM involvement, no exceptions."
      />

      {isLoading ? (
        <div className="space-y-2 rounded-2xl border border-border bg-surface/60 p-4">
          <SkeletonRow cols={4} />
          <SkeletonRow cols={4} />
        </div>
      ) : error || !data ? (
        <p className="text-sm text-status-danger font-mono">Could not load policy configuration.</p>
      ) : (
        <>
          <div className="space-y-3">
            <h3 className="text-xs font-mono font-semibold text-fg-secondary uppercase tracking-wider">
              Current Configuration
            </h3>
            <FeatureGrid
              items={[
                {
                  icon: ShieldCheck,
                  label: "Max Recovery Attempts",
                  value: data.config.max_recovery_attempts,
                },
                {
                  icon: ShieldCheck,
                  label: "Contact Window",
                  value: `${data.config.contact_window_hours}h`,
                },
                {
                  icon: ShieldCheck,
                  label: "Max Contacts / Window",
                  value: data.config.max_contacts_per_window,
                },
                {
                  icon: ShieldCheck,
                  label: "Auto-Approval Ceiling",
                  value: formatINR(data.config.auto_approval_amount_limit),
                  tone: "success",
                },
              ]}
            />
          </div>

          <div className="space-y-3">
            <h3 className="text-xs font-mono font-semibold text-fg-secondary uppercase tracking-wider">
              Rule → Condition → Decision → Restriction
            </h3>
            <div className="grid grid-cols-1 gap-px overflow-hidden rounded-2xl border border-hairline bg-[color:var(--hairline)] lg:grid-cols-2">
              {data.rules.map((rule) => {
                const t = toneFor(rule.decision);
                const Icon = t.icon;
                return (
                  <div key={rule.rule_id} className="bg-surface p-6 space-y-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-fg-faint">
                        {rule.rule_id}
                      </span>
                      <span
                        className={cn(
                          "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-mono font-semibold uppercase tracking-wide",
                          toneClasses[t.tone]
                        )}
                      >
                        <Icon className="h-3 w-3" />
                        {rule.decision.split("—")[0].trim()}
                      </span>
                    </div>
                    <h4 className="text-sm font-semibold text-fg">{rule.name}</h4>
                    <div className="space-y-1.5 text-xs">
                      <p>
                        <span className="font-mono text-fg-faint">CONDITION — </span>
                        <span className="text-fg-muted">{rule.condition}</span>
                      </p>
                      <p>
                        <span className="font-mono text-fg-faint">DECISION — </span>
                        <span className="text-fg-muted">{rule.decision}</span>
                      </p>
                      <p>
                        <span className="font-mono text-fg-faint">RESTRICTION — </span>
                        <span className="text-fg-muted">{rule.action_restriction}</span>
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="flex items-start gap-3 rounded-2xl border border-hairline bg-surface-subtle/60 p-5">
            <Scale className="h-5 w-5 shrink-0 text-fg-faint mt-0.5" />
            <div className="space-y-1">
              <p className="text-xs font-mono font-semibold uppercase tracking-wider text-fg-secondary">
                {data.editable ? "Editable" : "Read-only by design"}
              </p>
              <p className="text-xs leading-relaxed text-fg-muted">{data.note}</p>
            </div>
          </div>
        </>
      )}
    </AppShell>
  );
}
