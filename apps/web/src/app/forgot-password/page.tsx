"use client";

import React, { useState } from "react";
import Link from "next/link";
import { Loader2, Mail } from "lucide-react";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { api } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.forgotPassword(email);
      setSent(res.message);
    } catch (err: any) {
      setError(err?.message || "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout title="Reset your password" subtitle="We'll send a reset link if that email has an account">
      {sent ? (
        <p className="rounded-lg border border-status-info-border bg-status-info-bg px-3 py-2.5 text-sm text-status-info">
          {sent}
        </p>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs text-fg-muted">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="h-11 w-full rounded-lg border border-border bg-surface-subtle px-3.5 text-sm text-fg placeholder-fg-faint focus:border-accent focus:outline-none"
              placeholder="you@company.com"
              autoFocus
            />
          </div>

          {error && (
            <p className="rounded-lg border border-status-danger-border bg-status-danger-bg px-3 py-2 text-xs text-status-danger">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-accent text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />}
            {busy ? "Sending…" : "Send reset link"}
          </button>
        </form>
      )}

      <p className="mt-6 text-center text-xs text-fg-muted">
        <Link href="/login" className="text-accent hover:text-accent-hover">
          Back to sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
