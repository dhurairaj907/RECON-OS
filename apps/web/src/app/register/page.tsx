"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, UserPlus } from "lucide-react";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { api } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [organizationName, setOrganizationName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.register({ email, password, organization_name: organizationName });
      router.push("/onboarding");
      router.refresh();
    } catch (err: any) {
      setError(err?.message || "Registration failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout title="Create your organization" subtitle="Start recovering revenue with RECON OS">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="mb-1 block text-xs text-fg-muted">Organization name</label>
          <input
            type="text"
            required
            value={organizationName}
            onChange={(e) => setOrganizationName(e.target.value)}
            className="h-11 w-full rounded-lg border border-border bg-surface-subtle px-3.5 text-sm text-fg placeholder-fg-faint focus:border-accent focus:outline-none"
            placeholder="Acme Inc"
            autoFocus
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-fg-muted">Email</label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="h-11 w-full rounded-lg border border-border bg-surface-subtle px-3.5 text-sm text-fg placeholder-fg-faint focus:border-accent focus:outline-none"
            placeholder="you@company.com"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-fg-muted">Password</label>
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="h-11 w-full rounded-lg border border-border bg-surface-subtle px-3.5 text-sm text-fg placeholder-fg-faint focus:border-accent focus:outline-none"
            placeholder="At least 8 characters"
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
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
          {busy ? "Creating organization…" : "Create organization"}
        </button>
      </form>

      <p className="mt-6 text-center text-xs text-fg-muted">
        Already have an account?{" "}
        <Link href="/login" className="text-accent hover:text-accent-hover">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
