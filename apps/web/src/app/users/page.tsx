"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { ShieldAlert, Users as UsersIcon } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { SectionBand } from "@/components/modules/SectionBand";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonRow } from "@/components/ui/SkeletonLoader";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { api } from "@/lib/api";
import type { OrgUserListResponse, UserRole } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

const ROLES: UserRole[] = ["ADMIN", "OPERATOR", "APPROVER", "VIEWER"];

/**
 * ADMIN-only. Server-side role enforcement is the real authority (GET/PATCH
 * /api/v1/users both 403 for non-admins) — this page's own gating is UX
 * only, reusing the same generic error-display pattern every other page
 * already uses when a fetch fails, rather than building a dedicated 403
 * page.
 */
export default function UsersPage() {
  const { data, error, mutate } = useSWR<OrgUserListResponse>("/api/v1/users", () => api.getOrgUsers());
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [updateError, setUpdateError] = useState<string | null>(null);

  const isForbidden = error?.message?.includes("not permitted") || error?.message?.includes("403");

  const handleRoleChange = async (userId: string, role: string) => {
    setUpdatingId(userId);
    setUpdateError(null);
    try {
      await api.updateUserRole(userId, role);
      await mutate();
    } catch (err: any) {
      setUpdateError(err?.message || "Could not update role.");
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <AppShell>
      <SectionBand
        eyebrow="ADMIN"
        title="ORGANIZATION USERS"
        subtitle="Members of your organization and their RECON OS role."
      />

      {!data && !error ? (
        <div className="space-y-2 rounded-2xl border border-border bg-surface/60 p-4">
          <SkeletonRow cols={4} />
          <SkeletonRow cols={4} />
        </div>
      ) : isForbidden ? (
        <EmptyState
          icon={ShieldAlert}
          title="Admin access required"
          description="Only an organization ADMIN can view or manage users. Ask an admin for access."
        />
      ) : error || !data ? (
        <p className="text-sm text-status-danger font-mono">Could not load organization users.</p>
      ) : data.items.length === 0 ? (
        <EmptyState icon={UsersIcon} title="No users found" description="This organization has no members yet." />
      ) : (
        <div className="overflow-hidden rounded-2xl border border-border bg-surface/60 backdrop-blur-sm">
          {updateError && (
            <p className="border-b border-status-danger-border/40 bg-status-danger-bg/40 px-4 py-2 text-xs text-status-danger">
              {updateError}
            </p>
          )}
          <table className="w-full text-left text-sm">
            <thead className="bg-surface-elevated/80 font-mono text-xs uppercase tracking-[0.08em] text-fg-faint border-b border-hairline">
              <tr>
                <th className="py-3.5 px-4">Email</th>
                <th className="py-3.5 px-4">Role</th>
                <th className="py-3.5 px-4">Status</th>
                <th className="py-3.5 px-4 text-right">Last Login</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {data.items.map((u) => (
                <tr key={u.id}>
                  <td className="py-3.5 px-4 text-fg">{u.email}</td>
                  <td className="py-3.5 px-4">
                    <select
                      value={u.role}
                      disabled={updatingId === u.id}
                      onChange={(e) => handleRoleChange(u.id, e.target.value)}
                      className="h-9 rounded-lg border border-border bg-surface-subtle px-2.5 text-xs font-mono text-fg-secondary focus:border-accent focus:outline-none disabled:opacity-50"
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>{r}</option>
                      ))}
                    </select>
                  </td>
                  <td className="py-3.5 px-4">
                    <StatusBadge status={u.is_active ? "ACTIVE" : "INACTIVE"} />
                  </td>
                  <td className="py-3.5 px-4 text-right font-mono text-xs text-fg-muted">
                    {u.last_login_at ? formatDateTime(u.last_login_at) : "Never"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </AppShell>
  );
}
