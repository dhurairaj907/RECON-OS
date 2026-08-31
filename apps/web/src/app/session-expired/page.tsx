"use client";

import React from "react";
import Link from "next/link";
import { Clock } from "lucide-react";
import { AuthLayout } from "@/components/layout/AuthLayout";

export default function SessionExpiredPage() {
  return (
    <AuthLayout title="Session expired" subtitle="Your session has ended for security. Please sign in again.">
      <div className="flex flex-col items-center gap-4">
        <div className="flex h-12 w-12 items-center justify-center rounded-full border border-status-warning-border bg-status-warning-bg text-status-warning">
          <Clock className="h-5 w-5" />
        </div>
        <Link
          href="/login"
          className="flex h-11 w-full items-center justify-center rounded-lg bg-accent text-sm font-medium text-white transition-colors hover:bg-accent-hover"
        >
          Sign in again
        </Link>
      </div>
    </AuthLayout>
  );
}
