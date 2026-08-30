"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { Search, ChevronLeft, ChevronRight, User, Mail, Phone, Hash, Wallet, Repeat } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { DetailDrawer } from "@/components/layout/DetailDrawer";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonRow } from "@/components/ui/SkeletonLoader";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Reveal } from "@/components/spatial/Reveal";
import { SectionBand } from "@/components/modules/SectionBand";
import { FeatureGrid } from "@/components/modules/FeatureGrid";
import { api } from "@/lib/api";
import { Customer, PaginatedResponse, RecoveryCase } from "@/lib/types";
import { formatINR, formatDateTime, formatRelativeTime } from "@/lib/utils";

/**
 * The customers endpoint has no embedded recovery-history field (confirmed
 * against apps/api/schemas/customer.py), and recovery-cases has no
 * customer_id filter — only status/priority/search (case_number or
 * failure_reason). So this cross-references client-side: fetch a bounded
 * batch of cases (backend caps limit at 100) and filter by customer_id.
 * Correct for this dataset's scale; not a general solution for a very large
 * case volume. No backend change.
 */
function useCustomerRecoveryHistory(customer: Customer | null) {
  const { data, isLoading } = useSWR(
    customer ? ["customer-recovery-history", customer.id] : null,
    () => api.getRecoveryCases({ limit: 100 })
  );
  const cases: RecoveryCase[] =
    customer && data ? data.items.filter((c) => c.customer_id === customer.id) : [];
  return { cases, isLoading: isLoading && !!customer };
}

export default function CustomersPage() {
  const [page, setPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);

  const { data, error, mutate, isValidating } = useSWR<PaginatedResponse<Customer>>(
    [`/api/v1/customers`, page, searchQuery],
    () =>
      api.getCustomers({
        page,
        limit: 15,
        search: searchQuery || undefined,
      }),
    { refreshInterval: 3000 }
  );

  const totalPages = data ? Math.ceil(data.total / 15) : 1;
  const isLoading = !data && !error;

  const { cases: recoveryHistory, isLoading: isHistoryLoading } =
    useCustomerRecoveryHistory(selectedCustomer);

  return (
    <AppShell onRefresh={() => mutate()} isRefreshing={isValidating}>
      <SectionBand
        eyebrow="CUSTOMER DIRECTORY"
        title="CUSTOMER PROFILES"
        subtitle="Historical transaction aggregates and factual payment profiles."
      />

      <div className="flex items-center justify-end">
        <div className="text-xs font-mono text-fg-muted bg-surface px-3 py-1.5 rounded-lg border border-border">
          Total Customers: <span className="text-fg font-bold">{data?.total || 0}</span>
        </div>
      </div>

      {/* Filter bar + table stay visually tight to each other — one operational unit */}
      <div className="space-y-3">
      <div className="rounded-2xl border border-border bg-surface/60 p-4 backdrop-blur-sm flex items-center">
        <div className="relative flex-1 w-full">
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-fg-faint" />
          <input
            type="text"
            placeholder="Search by customer name, email, or phone number..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            className="w-full h-11 bg-surface-subtle border border-border rounded-lg pl-10 pr-4 text-sm text-fg placeholder-fg-faint focus:outline-none focus:border-accent"
          />
        </div>
      </div>

      {/* Customers Table */}
      <div className="overflow-hidden rounded-2xl border border-border bg-surface/60 backdrop-blur-sm">
        {isLoading ? (
          <div className="p-4 space-y-2">
            <SkeletonRow cols={6} />
            <SkeletonRow cols={6} />
            <SkeletonRow cols={6} />
          </div>
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            title="No customer profiles found"
            description="Customers are automatically indexed as webhook and payment events are received."
            actionText="Simulate Customer Event"
            actionHref="/simulator"
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 z-10 bg-surface-elevated/80 font-mono text-xs uppercase tracking-[0.08em] text-fg-faint border-b border-hairline backdrop-blur-sm">
                  <tr>
                    <th className="py-4 px-4">Customer Name</th>
                    <th className="py-4 px-4">Email / Phone</th>
                    <th className="py-4 px-4">Total Secured Revenue</th>
                    <th className="py-4 px-4">Successful</th>
                    <th className="py-4 px-4">Failed</th>
                    <th className="py-4 px-4 text-right">Last Activity</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline">
                  {data.items.map((cust) => (
                    <Reveal
                      key={cust.id}
                      as="tr"
                      onClick={() => setSelectedCustomer(cust)}
                      className="cursor-pointer border-l-2 border-transparent transition-colors hover:border-accent hover:bg-surface-elevated/40"
                    >
                      <td className="py-4 px-4 font-medium text-fg">
                        {cust.name || "Customer"}
                      </td>
                      <td className="py-4 px-4 font-mono text-fg-muted">
                        {cust.email || cust.phone || "—"}
                      </td>
                      <td className="py-4 px-4 font-mono font-semibold text-status-success tabular-nums">
                        {formatINR(cust.total_payment_amount)}
                      </td>
                      <td className="py-4 px-4 font-mono text-status-success">
                        {cust.successful_payment_count}
                      </td>
                      <td className="py-4 px-4 font-mono text-status-danger">
                        {cust.failed_payment_count}
                      </td>
                      <td className="py-4 px-4 text-right font-mono text-fg-muted">
                        {cust.last_payment_at ? formatRelativeTime(cust.last_payment_at) : "—"}
                      </td>
                    </Reveal>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            <div className="flex items-center justify-between px-4 py-3 border-t border-border bg-surface-subtle text-xs font-mono text-fg-muted">
              <div>
                Page <span className="text-fg font-medium">{page}</span> of{" "}
                <span className="text-fg font-medium">{totalPages || 1}</span>
              </div>
              <div className="flex items-center space-x-2">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface border border-border disabled:opacity-40 hover:bg-surface-elevated text-fg-secondary"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface border border-border disabled:opacity-40 hover:bg-surface-elevated text-fg-secondary"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
      </div>

      {/* Customer Detail Drawer */}
      <DetailDrawer
        isOpen={!!selectedCustomer}
        onClose={() => setSelectedCustomer(null)}
        title={selectedCustomer?.name || "Customer Profile"}
        subtitle={`First seen ${formatDateTime(selectedCustomer?.created_at)}`}
      >
        {selectedCustomer && (
          <div className="space-y-6 text-xs">
            {/* Financial relationship */}
            <div className="space-y-3">
              <h3 className="text-xs font-mono font-semibold text-fg-secondary uppercase tracking-wider">
                Financial Relationship
              </h3>
              <FeatureGrid
                items={[
                  {
                    icon: Wallet,
                    label: "Total Paid",
                    value: formatINR(selectedCustomer.total_payment_amount),
                    tone: "success",
                  },
                  {
                    icon: Repeat,
                    label: "Total Transactions",
                    value:
                      selectedCustomer.successful_payment_count +
                      selectedCustomer.failed_payment_count,
                  },
                ]}
              />
            </div>

            {/* Identity */}
            <div className="space-y-3">
              <h3 className="text-xs font-mono font-semibold text-fg-secondary uppercase tracking-wider">
                Identity & Contact
              </h3>
              <FeatureGrid
                items={[
                  { icon: User, label: "Name", value: selectedCustomer.name || "N/A" },
                  { icon: Mail, label: "Email", value: selectedCustomer.email || "N/A", tone: "info" },
                  { icon: Phone, label: "Phone", value: selectedCustomer.phone || "N/A" },
                  {
                    icon: Hash,
                    label: "Razorpay Customer ID",
                    value: selectedCustomer.razorpay_customer_id || "None",
                  },
                ]}
              />
            </div>

            {/* Recovery History — client-side cross-reference, see useCustomerRecoveryHistory above */}
            <div className="space-y-3">
              <h3 className="text-xs font-mono font-semibold text-fg-secondary uppercase tracking-wider">
                Recovery History
              </h3>
              {isHistoryLoading ? (
                <SkeletonRow cols={4} />
              ) : recoveryHistory.length === 0 ? (
                <p className="p-3 rounded-lg bg-surface-subtle border border-border text-fg-faint font-mono text-[11px]">
                  No recovery cases for this customer.
                </p>
              ) : (
                <div className="divide-y divide-hairline rounded-lg border border-border bg-surface-subtle overflow-hidden">
                  {recoveryHistory.map((rc) => (
                    <div key={rc.id} className="flex items-center justify-between p-3 gap-3">
                      <div className="min-w-0">
                        <div className="font-mono text-status-info font-medium">{rc.case_number}</div>
                        <div className="text-[11px] text-fg-faint truncate">
                          {rc.failure_reason || "—"} · {formatRelativeTime(rc.opened_at)}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="font-mono text-xs text-status-danger tabular-nums">
                          {formatINR(rc.amount_at_risk)}
                        </span>
                        <StatusBadge status={rc.status} type="case" />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </DetailDrawer>
    </AppShell>
  );
}
