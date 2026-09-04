"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { Mail, MessageSquare, Send, Loader2, Ban, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import type { CommunicationChannel, CommunicationMessageType } from "@/lib/types";
import { cn, formatDateTime } from "@/lib/utils";
import { deriveCommunicationsPresentation } from "./communications-model";

const CHANNELS: { value: CommunicationChannel; label: string; icon: typeof Mail }[] = [
  { value: "EMAIL", label: "Email", icon: Mail },
  { value: "SMS", label: "SMS", icon: MessageSquare },
  { value: "WHATSAPP", label: "WhatsApp", icon: MessageSquare },
];
const MESSAGE_TYPES: { value: CommunicationMessageType; label: string }[] = [
  { value: "PAYMENT_FAILED", label: "Payment Failed" },
  { value: "PAYMENT_LINK_CREATED", label: "Payment Link Created" },
  { value: "PAYMENT_RECOVERY", label: "Payment Recovery" },
  { value: "RECOVERY_REMINDER", label: "Recovery Reminder" },
  { value: "PAYMENT_RECOVERED", label: "Payment Recovered" },
];

const statusTone: Record<string, string> = {
  SENT: "text-status-success border-status-success-border bg-status-success-bg",
  DELIVERED: "text-status-success border-status-success-border bg-status-success-bg",
  FAILED: "text-status-danger border-status-danger-border bg-status-danger-bg",
  OPTED_OUT: "text-status-danger border-status-danger-border bg-status-danger-bg",
  SKIPPED: "text-status-warning border-status-warning-border bg-status-warning-bg",
  CANCELLED: "text-status-warning border-status-warning-border bg-status-warning-bg",
  QUEUED: "text-status-info border-status-info-border bg-status-info-bg",
  SENDING: "text-status-info border-status-info-border bg-status-info-bg",
};

// A provider only ever ACCEPTS a request (SENT) — DELIVERED requires a real,
// separate delivery confirmation (see routers/communication_webhooks.py).
// NOT_CONFIGURED is a FAILED send whose error_code says so; surfaced here
// distinctly so an operator never mistakes "no provider configured" for a
// transient provider failure.
function statusLabel(c: { status: string; error_code?: string | null }): string {
  if (c.status === "FAILED" && c.error_code === "NOT_CONFIGURED") return "NOT CONFIGURED";
  return c.status;
}

/**
 * Communication history + send control for a recovery case — the customer-
 * facing counterpart to the Action section above it. Sending always goes
 * through POST /recovery-cases/{id}/communications/send, which re-derives
 * eligibility server-side (Policy Engine + human-approval state) — this
 * component never decides whether a message is allowed, only whether to ask.
 */
export function CommunicationsSection({
  caseId,
  automaticCommunicationsEnabled = false,
}: {
  caseId: string;
  automaticCommunicationsEnabled?: boolean;
}) {
  const { data, mutate } = useSWR(
    caseId ? `/api/v1/recovery-cases/${caseId}/communications` : null,
    () => api.getCaseCommunications(caseId),
    { refreshInterval: 5000 }
  );
  const [channel, setChannel] = useState<CommunicationChannel>("EMAIL");
  const [messageType, setMessageType] = useState<CommunicationMessageType>("PAYMENT_LINK_CREATED");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  const handleSend = async () => {
    setBusy(true);
    setResult(null);
    try {
      const res = await api.sendCommunication(caseId, channel, messageType);
      setResult({ ok: res.ok, message: res.message });
      await mutate();
    } catch (e: any) {
      setResult({ ok: false, message: e?.message || "Request failed." });
    } finally {
      setBusy(false);
    }
  };

  const items = data?.items || [];
  const cp = deriveCommunicationsPresentation(automaticCommunicationsEnabled);

  const sendControls = (
    <>
      <select
        value={channel}
        onChange={(e) => setChannel(e.target.value as CommunicationChannel)}
        className={cn(
          "rounded-lg border border-border bg-surface-subtle font-mono text-fg-secondary focus:border-accent focus:outline-none",
          cp.showSendAsPrimary ? "h-9 px-2.5 text-xs" : "h-8 px-2 text-[11px]"
        )}
      >
        {CHANNELS.map((c) => (
          <option key={c.value} value={c.value}>{c.label}</option>
        ))}
      </select>
      <select
        value={messageType}
        onChange={(e) => setMessageType(e.target.value as CommunicationMessageType)}
        className={cn(
          "rounded-lg border border-border bg-surface-subtle font-mono text-fg-secondary focus:border-accent focus:outline-none",
          cp.showSendAsPrimary ? "h-9 px-2.5 text-xs" : "h-8 px-2 text-[11px]"
        )}
      >
        {MESSAGE_TYPES.map((m) => (
          <option key={m.value} value={m.value}>{m.label}</option>
        ))}
      </select>
      {cp.showSendAsPrimary ? (
        <button
          onClick={handleSend}
          disabled={busy}
          className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-accent px-3 font-mono text-xs font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
          Send
        </button>
      ) : (
        <button
          onClick={handleSend}
          disabled={busy}
          className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-surface-subtle px-2.5 font-mono text-[11px] text-fg-secondary transition-colors hover:bg-surface-elevated hover:text-fg disabled:opacity-50"
        >
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
          Send manually now instead of waiting
        </button>
      )}
    </>
  );

  return (
    <div className="space-y-3 border-t border-border/60 pt-4">
      <div className="flex items-center justify-between">
        <h4 className="text-[12px] font-mono font-semibold text-fg-secondary uppercase tracking-widest">
          Communications
        </h4>
        <span className="text-[11px] font-mono text-fg-faint">{items.length} sent/attempted</span>
      </div>

      {cp.mode === "automatic" ? (
        <div className="rounded-lg border border-status-success-border/40 bg-status-success-bg/30 px-3 py-2 space-y-2">
          <p className="flex items-center gap-1.5 text-[12px] font-mono font-semibold text-status-success">
            <Sparkles className="h-3.5 w-3.5" /> {cp.headline}
          </p>
          <p className="text-[11px] font-mono text-fg-faint leading-relaxed">{cp.detail}</p>
          <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-status-success-border/30">
            {sendControls}
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          <p className="text-[11px] font-mono text-fg-faint">{cp.detail}</p>
          <div className="flex flex-wrap items-center gap-2">{sendControls}</div>
        </div>
      )}

      {result && (
        <p
          className={cn(
            "rounded border px-2.5 py-1.5 text-[12px] font-mono",
            result.ok
              ? "border-status-success-border/50 bg-status-success-bg text-status-success"
              : "border-status-warning-border/50 bg-status-warning-bg text-status-warning"
          )}
        >
          {result.message}
        </p>
      )}

      {items.length > 0 && (
        <div className="divide-y divide-hairline rounded-lg border border-border bg-surface-subtle/40 overflow-hidden">
          {items.map((c) => (
            <div key={c.id} className="flex items-center justify-between gap-3 p-3 text-[12px] font-mono">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-fg-secondary">{c.channel}</span>
                  <span className="text-fg-faint">·</span>
                  <span className="text-fg-muted">{c.message_type}</span>
                </div>
                <div className="mt-0.5 truncate text-[11px] text-fg-faint">
                  {c.status === "FAILED" && c.error_message
                    ? c.error_message
                    : c.skipped_reason
                    ? c.skipped_reason.replace(/_/g, " ")
                    : c.provider || ""}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span className="text-[11px] text-fg-faint">{formatDateTime(c.created_at)}</span>
                <span
                  className={cn(
                    "inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[10px] font-semibold uppercase",
                    statusTone[c.status] || "text-fg-muted border-border bg-surface-elevated"
                  )}
                >
                  {c.status === "FAILED" || c.status === "OPTED_OUT" || c.status === "CANCELLED" ? (
                    <Ban className="h-3 w-3" />
                  ) : null}
                  {statusLabel(c)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
