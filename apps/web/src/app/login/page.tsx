"use client";

import React, { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2, LogIn } from "lucide-react";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { api } from "@/lib/api";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login({ email, password });
      const next = searchParams.get("next") || "/";
      router.push(next);
      router.refresh();
    } catch (err: any) {
      setError(err?.message || "Login failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
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
        <div>
          <div className="mb-1 flex items-center justify-between">
            <label className="block text-xs text-fg-muted">Password</label>
            <Link href="/forgot-password" className="text-xs text-accent hover:text-accent-hover">
              Forgot password?
            </Link>
          </div>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="h-11 w-full rounded-lg border border-border bg-surface-subtle px-3.5 text-sm text-fg placeholder-fg-faint focus:border-accent focus:outline-none"
            placeholder="••••••••"
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
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogIn className="h-4 w-4" />}
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>

      <p className="mt-6 text-center text-xs text-fg-muted">
        Don&apos;t have an organization yet?{" "}
        <Link href="/register" className="text-accent hover:text-accent-hover">
          Create one
        </Link>
      </p>
    </>
  );
}

export default function LoginPage() {
  return (
    <AuthLayout title="Sign in to RECON OS" subtitle="Revenue recovery command center">
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </AuthLayout>
  );
}
