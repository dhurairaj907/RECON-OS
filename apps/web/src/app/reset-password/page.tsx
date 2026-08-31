"use client";

import React, { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2, KeyRound, Loader2 } from "lucide-react";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { api } from "@/lib/api";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";
  const [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.resetPassword({ token, new_password: newPassword });
      setDone(true);
    } catch (err: any) {
      setError(err?.message || "Could not reset password — the link may have expired.");
    } finally {
      setBusy(false);
    }
  };

  if (!token) {
    return (
      <p className="rounded-lg border border-status-danger-border bg-status-danger-bg px-3 py-2 text-sm text-status-danger">
        This reset link is missing its token. Request a new one from the{" "}
        <Link href="/forgot-password" className="underline">
          forgot password
        </Link>{" "}
        page.
      </p>
    );
  }

  if (done) {
    return (
      <div className="space-y-4 text-center">
        <CheckCircle2 className="mx-auto h-8 w-8 text-status-success" />
        <p className="text-sm text-fg-muted">Your password has been reset.</p>
        <Link
          href="/login"
          className="inline-flex h-10 items-center rounded-lg bg-accent px-4 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
        >
          Sign in
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="mb-1 block text-xs text-fg-muted">New password</label>
        <input
          type="password"
          required
          minLength={8}
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          className="h-11 w-full rounded-lg border border-border bg-surface-subtle px-3.5 text-sm text-fg placeholder-fg-faint focus:border-accent focus:outline-none"
          placeholder="At least 8 characters"
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
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
        {busy ? "Resetting…" : "Reset password"}
      </button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <AuthLayout title="Set a new password" subtitle="This resets your account password">
      <Suspense fallback={null}>
        <ResetPasswordForm />
      </Suspense>
    </AuthLayout>
  );
}
