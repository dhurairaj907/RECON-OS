"use client";

import React, { useState } from "react";
import {
  FlaskConical,
  Play,
  CheckCircle,
  AlertCircle,
  Clock,
  CreditCard,
  Building,
  Zap,
  Terminal,
  ShieldAlert,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { api } from "@/lib/api";
import { SimulateEventRequest, SimulateEventResponse } from "@/lib/types";
import { formatINR } from "@/lib/utils";

interface PresetScenario {
  id: string;
  name: string;
  description: string;
  icon: any;
  request: SimulateEventRequest;
}

const PRESET_SCENARIOS: PresetScenario[] = [
  {
    id: "upi_timeout",
    name: "UPI Session Timeout",
    description: "Customer initiated UPI payment but timed out before entering PIN.",
    icon: Clock,
    request: {
      event_type: "payment.failed",
      customer_name: "Rahul Sharma",
      customer_email: "rahul.sharma@example.com",
      customer_phone: "+919876543210",
      amount: "4999.00",
      payment_method: "upi",
      failure_code: "BAD_REQUEST_ERROR",
      failure_reason: "payment_failed",
      error_description: "UPI handle authorization timeout on customer app",
    },
  },
  {
    id: "card_declined",
    name: "Card Insufficient Funds",
    description: "Credit card transaction declined by issuing bank due to limits.",
    icon: CreditCard,
    request: {
      event_type: "payment.failed",
      customer_name: "Priya Patel",
      customer_email: "priya.patel@techcorp.in",
      customer_phone: "+919812345678",
      amount: "14999.00",
      payment_method: "card",
      failure_code: "GATEWAY_ERROR",
      failure_reason: "payment_failed",
      error_description: "Transaction declined: Insufficient funds / limit exceeded",
    },
  },
  {
    id: "corp_critical",
    name: "High-Value Corporate Failure",
    description: "Enterprise SaaS invoice failure (>= ₹50,000) triggering CRITICAL priority case.",
    icon: Building,
    request: {
      event_type: "payment.failed",
      customer_name: "Acme Enterprises Ltd",
      customer_email: "finance@acme-enterprises.com",
      customer_phone: "+919988776655",
      amount: "75000.00",
      payment_method: "netbanking",
      failure_code: "BAD_REQUEST_ERROR",
      failure_reason: "payment_failed",
      error_description: "Corporate netbanking approval limit exceeded",
    },
  },
  {
    id: "fraud_risk_block",
    name: "Fraud / Risk Block",
    description: "Payment blocked by the risk engine. Policy must REJECT any automatic retry.",
    icon: ShieldAlert,
    request: {
      event_type: "payment.failed",
      customer_name: "Vikram Singh",
      customer_email: "vikram.singh@example.com",
      customer_phone: "+919900112233",
      amount: "4999.00",
      payment_method: "card",
      failure_code: "BAD_REQUEST_ERROR",
      failure_reason: "payment_risk_check_failed",
      error_description: "Payment blocked by risk engine — suspected fraudulent transaction",
    },
  },
  {
    id: "payment_captured",
    name: "Successful Payment Captured",
    description: "Payment captured successfully. Resolves open recovery cases for this payment.",
    icon: CheckCircle,
    request: {
      event_type: "payment.captured",
      customer_name: "Rahul Sharma",
      customer_email: "rahul.sharma@example.com",
      customer_phone: "+919876543210",
      amount: "4999.00",
      payment_method: "upi",
      failure_code: "",
      failure_reason: "",
      error_description: "",
    },
  },
];

export default function SimulatorPage() {
  const [isExecuting, setIsExecuting] = useState(false);
  const [logs, setLogs] = useState<Array<{ timestamp: string; type: "info" | "success" | "error"; text: string }>>([
    {
      timestamp: new Date().toLocaleTimeString(),
      type: "info",
      text: "RECON Event Simulator Laboratory ready. Select a preset or customize parameters.",
    },
  ]);
  const [lastResult, setLastResult] = useState<SimulateEventResponse | null>(null);

  // Custom form state
  const [form, setForm] = useState<SimulateEventRequest>({
    event_type: "payment.failed",
    customer_name: "Test Customer",
    customer_email: "test.customer@reconos.io",
    customer_phone: "+919876543210",
    amount: "8499.00",
    payment_method: "upi",
    failure_code: "BAD_REQUEST_ERROR",
    failure_reason: "payment_failed",
    error_description: "Payment processing failed",
  });

  const addLog = (type: "info" | "success" | "error", text: string) => {
    setLogs((prev) => [
      { timestamp: new Date().toLocaleTimeString(), type, text },
      ...prev.slice(0, 19), // keep last 20 logs
    ]);
  };

  const handleTrigger = async (req: SimulateEventRequest) => {
    setIsExecuting(true);
    addLog("info", `Dispatching simulated ${req.event_type} (${formatINR(req.amount)}) to /api/v1/simulator/events...`);

    try {
      // Direct call to real backend pipeline
      const res = await api.triggerSimulation(req);
      setLastResult(res);

      if (res.success) {
        addLog(
          "success",
          `✓ Event persisted: ${res.razorpay_event_id} | Status: ${res.processing_status}`
        );
        if (res.case_number) {
          addLog("success", `✓ Recovery Case generated: ${res.case_number} (Status: DETECTED)`);
        }
      } else {
        addLog("error", `✗ Simulation failed: ${res.message}`);
      }
    } catch (err: any) {
      addLog("error", `✗ Network/Server error: ${err.message}`);
    } finally {
      setIsExecuting(false);
    }
  };

  return (
    <AppShell>
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-6">
        <div>
          <div className="flex items-center space-x-2">
            <FlaskConical className="w-4 h-4 text-accent" />
            <span className="text-xs font-mono tracking-wider text-slate-400 uppercase">
              Event Simulation Lab
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white font-mono mt-1">
            RECON EVENT SIMULATOR
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Generate controlled Razorpay-format payment events and execute them through the real backend pipeline.
          </p>
        </div>

        <div className="flex items-center space-x-2 text-xs font-mono text-slate-400 bg-surface px-3 py-1.5 rounded-lg border border-border">
          <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
          <span>Backend Pipeline Active</span>
        </div>
      </div>

      {/* Preset Scenarios Grid */}
      <div>
        <h2 className="text-sm font-semibold text-white tracking-wide font-mono mb-3">
          PRESET PAYMENT SCENARIOS
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {PRESET_SCENARIOS.map((preset) => {
            const Icon = preset.icon;
            return (
              <div
                key={preset.id}
                className="bg-surface p-5 rounded-lg border border-border hover:border-border-highlight transition-all flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <div className="p-2 rounded-md bg-surface-subtle border border-border text-blue-400">
                      <Icon className="w-4 h-4" />
                    </div>
                    <StatusBadge status={preset.request.event_type} type="event" />
                  </div>
                  <h3 className="text-sm font-semibold text-white mt-3">{preset.name}</h3>
                  <p className="text-xs text-slate-400 mt-1">{preset.description}</p>
                  <div className="mt-3 font-mono text-xs font-bold text-slate-200">
                    Amount: {formatINR(preset.request.amount)}
                  </div>
                </div>

                <button
                  disabled={isExecuting}
                  onClick={() => handleTrigger(preset.request)}
                  className="mt-4 w-full flex items-center justify-center space-x-1.5 px-3 py-2 rounded-lg bg-accent text-white text-xs font-mono font-medium hover:bg-accent-hover transition-colors disabled:opacity-50"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>{isExecuting ? "Executing..." : "Trigger Event"}</span>
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {/* Custom Event Builder & Live Execution Console */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Custom Event Form */}
        <div className="bg-surface p-6 rounded-lg border border-border space-y-4">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <div>
              <h2 className="text-sm font-semibold text-white tracking-wide font-mono">
                CUSTOM EVENT BUILDER
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Configure custom customer, amount, and failure parameters
              </p>
            </div>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleTrigger(form);
            }}
            className="space-y-4 text-xs font-mono"
          >
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-slate-400 block mb-1">Event Type</label>
                <select
                  value={form.event_type}
                  onChange={(e) => setForm({ ...form, event_type: e.target.value })}
                  className="w-full bg-surface-subtle border border-border rounded px-3 py-1.5 text-white focus:outline-none focus:border-accent"
                >
                  <option value="payment.failed">payment.failed</option>
                  <option value="payment.captured">payment.captured</option>
                  <option value="payment.authorized">payment.authorized</option>
                </select>
              </div>
              <div>
                <label className="text-slate-400 block mb-1">Payment Method</label>
                <select
                  value={form.payment_method}
                  onChange={(e) => setForm({ ...form, payment_method: e.target.value })}
                  className="w-full bg-surface-subtle border border-border rounded px-3 py-1.5 text-white focus:outline-none focus:border-accent"
                >
                  <option value="upi">UPI</option>
                  <option value="card">Credit / Debit Card</option>
                  <option value="netbanking">Net Banking</option>
                  <option value="wallet">Wallet</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-slate-400 block mb-1">Amount (INR)</label>
                <input
                  type="number"
                  step="0.01"
                  value={form.amount}
                  onChange={(e) => setForm({ ...form, amount: e.target.value })}
                  className="w-full bg-surface-subtle border border-border rounded px-3 py-1.5 text-white focus:outline-none focus:border-accent"
                  required
                />
              </div>
              <div>
                <label className="text-slate-400 block mb-1">Customer Name</label>
                <input
                  type="text"
                  value={form.customer_name}
                  onChange={(e) => setForm({ ...form, customer_name: e.target.value })}
                  className="w-full bg-surface-subtle border border-border rounded px-3 py-1.5 text-white focus:outline-none focus:border-accent"
                  required
                />
              </div>
            </div>

            <div>
              <label className="text-slate-400 block mb-1">Customer Email</label>
              <input
                type="email"
                value={form.customer_email}
                onChange={(e) => setForm({ ...form, customer_email: e.target.value })}
                className="w-full bg-surface-subtle border border-border rounded px-3 py-1.5 text-white focus:outline-none focus:border-accent"
                required
              />
            </div>

            {form.event_type === "payment.failed" && (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-slate-400 block mb-1">Error Code</label>
                  <input
                    type="text"
                    value={form.failure_code || ""}
                    onChange={(e) => setForm({ ...form, failure_code: e.target.value })}
                    className="w-full bg-surface-subtle border border-border rounded px-3 py-1.5 text-white focus:outline-none focus:border-accent"
                  />
                </div>
                <div>
                  <label className="text-slate-400 block mb-1">Error Description</label>
                  <input
                    type="text"
                    value={form.error_description || ""}
                    onChange={(e) => setForm({ ...form, error_description: e.target.value })}
                    className="w-full bg-surface-subtle border border-border rounded px-3 py-1.5 text-white focus:outline-none focus:border-accent"
                  />
                </div>
              </div>
            )}

            <button
              type="submit"
              disabled={isExecuting}
              className="w-full flex items-center justify-center space-x-2 py-2.5 rounded-lg bg-accent text-white font-medium hover:bg-accent-hover transition-colors disabled:opacity-50 mt-2"
            >
              <Play className="w-4 h-4 fill-current" />
              <span>{isExecuting ? "Processing via Backend Pipeline..." : "Dispatch Custom Event"}</span>
            </button>
          </form>
        </div>

        {/* Live Execution Console */}
        <div className="bg-surface rounded-lg border border-border flex flex-col overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-border bg-surface-subtle">
            <div className="flex items-center space-x-2">
              <Terminal className="w-4 h-4 text-emerald-400" />
              <h2 className="text-xs font-semibold text-white tracking-wide font-mono uppercase">
                PIPELINE EXECUTION CONSOLE
              </h2>
            </div>
            <span className="text-[10px] font-mono text-slate-500">Live Stream</span>
          </div>

          <div className="p-4 flex-1 bg-surface-subtle/70 font-mono text-xs overflow-y-auto max-h-96 space-y-2 select-text">
            {logs.map((log, i) => (
              <div
                key={i}
                className={`p-2 rounded border leading-relaxed ${
                  log.type === "success"
                    ? "bg-status-success-bg/40 border-status-success-border/40 text-emerald-300"
                    : log.type === "error"
                    ? "bg-status-danger-bg/40 border-status-danger-border/40 text-rose-300"
                    : "bg-surface border-border/80 text-slate-300"
                }`}
              >
                <span className="text-[10px] text-slate-500 mr-2">[{log.timestamp}]</span>
                {log.text}
              </div>
            ))}
          </div>

          {lastResult && (
            <div className="p-3 border-t border-border bg-surface text-xs font-mono flex items-center justify-between text-slate-300">
              <span>Last Event ID: <strong className="text-white">{lastResult.razorpay_event_id}</strong></span>
              {lastResult.case_number && (
                <span className="text-blue-400 font-semibold">Case: {lastResult.case_number}</span>
              )}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
