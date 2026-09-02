"use client";

import React from "react";
import useSWR from "swr";
import { Zap, Mail, MessageSquare, Phone, Webhook, Bot } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { SectionBand } from "@/components/modules/SectionBand";
import { FeatureGrid, type FeatureGridItem } from "@/components/modules/FeatureGrid";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

const STATUS_TONE: Record<string, FeatureGridItem["tone"]> = {
  CONNECTED: "success",
  FAKE_MODE: "warning",
  NOT_CONFIGURED: "danger",
  INVALID_CREDENTIALS: "danger",
  WEBHOOK_NOT_CONFIGURED: "warning",
};

/**
 * Read-only connections/integrations status — every field here is computed
 * from existing server-side config (config.settings), the existing Razorpay
 * adapter, and the existing RevenueEvent table (already populated by the
 * real webhook handler and the Simulator). No secrets are ever exposed.
 *
 * This is deliberately READ-ONLY: RECON OS has no per-organization
 * encrypted credential store yet, so there is no safe "Connect"/"Disconnect"
 * flow to offer here without inventing insecure secret storage. Provider
 * credentials remain server-side environment configuration, exactly as in
 * every prior phase.
 */
export default function ConnectionsPage() {
  const { data, error, isLoading } = useSWR("/api/v1/connections", () => api.getConnections(), {
    refreshInterval: 15000,
  });

  return (
    <AppShell>
      <SectionBand
        eyebrow="INTEGRATIONS"
        title="CONNECTIONS"
        subtitle="Real, server-verified status for every payment and communication provider RECON is configured to use."
      />

      {isLoading && !data ? (
        <p className="text-sm text-fg-muted font-mono">Loading connection status…</p>
      ) : error || !data ? (
        <p className="text-sm text-status-danger font-mono">Could not load connection status.</p>
      ) : (
        <div className="space-y-8">
          <div className="space-y-3">
            <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-fg-secondary">
              Payment Provider
            </h3>
            <FeatureGrid
              items={[
                {
                  icon: Zap, label: "Razorpay",
                  value: data.razorpay.status.replace(/_/g, " "),
                  tone: STATUS_TONE[data.razorpay.status] ?? "default",
                },
                { icon: Zap, label: "Mode", value: data.razorpay.test_mode ? "TEST" : "LIVE" },
                {
                  icon: Webhook, label: "Webhook Signature",
                  value: data.razorpay.webhook_secret_set ? "Configured (verified)" : "Not configured",
                  tone: data.razorpay.webhook_secret_set ? "success" : "warning",
                },
                {
                  icon: Zap, label: "Simulator (test lane)",
                  value: data.razorpay.simulator_enabled ? "Enabled" : "Disabled",
                  tone: data.razorpay.simulator_enabled ? "warning" : "default",
                },
                {
                  icon: Webhook, label: "Last Event Received",
                  value: data.razorpay.last_event_at ? formatDateTime(data.razorpay.last_event_at) : "None yet",
                },
                {
                  icon: Webhook, label: "Last Successful Event",
                  value: data.razorpay.last_success_at ? formatDateTime(data.razorpay.last_success_at) : "None yet",
                  tone: data.razorpay.last_success_at ? "success" : "default",
                },
                {
                  icon: Webhook, label: "Last Failed Event",
                  value: data.razorpay.last_failure_at
                    ? `${formatDateTime(data.razorpay.last_failure_at)}${data.razorpay.last_error ? ` — ${data.razorpay.last_error}` : ""}`
                    : "None",
                  tone: data.razorpay.last_failure_at ? "danger" : "default",
                },
                { icon: Webhook, label: "Events Received (recent)", value: data.razorpay.events_received_total },
              ]}
            />
            <p className="text-[11px] font-mono text-fg-faint">{data.razorpay.connection_scope}</p>
          </div>

          <div className="space-y-3">
            <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-fg-secondary">
              Communication Providers
            </h3>
            <FeatureGrid
              items={[
                {
                  icon: Mail, label: "Email / SMTP",
                  value: data.email.status.replace(/_/g, " "),
                  tone: STATUS_TONE[data.email.status] ?? "default",
                },
                {
                  icon: MessageSquare, label: "SMS",
                  value: data.sms.status.replace(/_/g, " "),
                  tone: STATUS_TONE[data.sms.status] ?? "default",
                },
                {
                  icon: Phone, label: "WhatsApp",
                  value: data.whatsapp.status.replace(/_/g, " "),
                  tone: STATUS_TONE[data.whatsapp.status] ?? "default",
                },
                { icon: Mail, label: "Communications Mode", value: data.email.mode.toUpperCase() },
              ]}
            />
            <p className="text-[11px] font-mono text-fg-faint">
              FAKE MODE never reaches a real provider — safe for development/demo. Switch to REAL mode
              (server-side configuration) to send genuine email/SMS/WhatsApp.
            </p>
          </div>

          <div className="space-y-3">
            <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-fg-secondary">
              Automation
            </h3>
            <FeatureGrid
              items={[
                {
                  icon: Bot, label: "Automatic Recovery Execution",
                  value: data.automation.automatic_action_execution_enabled ? "ON" : "OFF",
                  tone: data.automation.automatic_action_execution_enabled ? "success" : "default",
                },
                {
                  icon: Bot, label: "Automatic Communications",
                  value: data.automation.automatic_communications_enabled ? "ON" : "OFF",
                  tone: data.automation.automatic_communications_enabled ? "success" : "default",
                },
              ]}
            />
            <p className="text-[11px] font-mono text-fg-faint">
              When Automatic Recovery Execution is ON, Policy-approved recovery actions execute
              without a manual click. The Policy Engine still independently authorizes every action —
              this setting only controls whether a human has to press the button.
            </p>
          </div>
        </div>
      )}
    </AppShell>
  );
}
