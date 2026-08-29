"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { Search, Users, ChevronLeft, ChevronRight, UserCheck, AlertTriangle } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { DetailDrawer } from "@/components/layout/DetailDrawer";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonRow } from "@/components/ui/SkeletonLoader";
import { api } from "@/lib/api";
import { Customer, PaginatedResponse } from "@/lib/types";
import { formatINR, formatDateTime, formatRelativeTime } from "@/lib/utils";

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

  return (
    <AppShell onRefresh={() => mutate()} isRefreshing={isValidating}>
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-6">
        <div>
          <div className="flex items-center space-x-2">
            <Users className="w-4 h-4 text-status-success" />
            <span className="text-xs font-mono tracking-wider text-fg-muted uppercase">
              Customer Directory
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-fg font-mono mt-1">
            CUSTOMER PROFILES
          </h1>
          <p className="text-xs text-fg-muted mt-1">
            Historical transaction aggregates and factual payment profiles.
          </p>
        </div>

        <div className="text-xs font-mono text-fg-muted bg-surface px-3 py-1.5 rounded-lg border border-border">
          Total Customers: <span className="text-fg font-bold">{data?.total || 0}</span>
        </div>
      </div>

      {/* Search Bar */}
      <div className="bg-surface p-4 rounded-lg border border-border flex items-center">
        <div className="relative flex-1 w-full">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-fg-faint" />
          <input
            type="text"
            placeholder="Search by customer name, email, or phone number..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            className="w-full bg-surface-subtle border border-border rounded-lg pl-9 pr-4 py-1.5 text-xs text-fg placeholder-fg-faint focus:outline-none focus:border-accent"
          />
        </div>
      </div>

      {/* Customers Table */}
      <div className="bg-surface rounded-lg border border-border overflow-hidden">
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
              <table className="w-full text-left text-xs">
                <thead className="bg-surface-elevated/50 text-fg-muted font-mono text-[11px] uppercase border-b border-border">
                  <tr>
                    <th className="py-3 px-4">Customer Name</th>
                    <th className="py-3 px-4">Email / Phone</th>
                    <th className="py-3 px-4">Total Secured Revenue</th>
                    <th className="py-3 px-4">Successful</th>
                    <th className="py-3 px-4">Failed</th>
                    <th className="py-3 px-4 text-right">Last Activity</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {data.items.map((cust) => (
                    <tr
                      key={cust.id}
                      onClick={() => setSelectedCustomer(cust)}
                      className="hover:bg-surface-elevated/40 cursor-pointer transition-colors"
                    >
                      <td className="py-3 px-4 font-medium text-fg">
                        {cust.name || "Customer"}
                      </td>
                      <td className="py-3 px-4 font-mono text-fg-muted">
                        {cust.email || cust.phone || "—"}
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-status-success tabular-nums">
                        {formatINR(cust.total_payment_amount)}
                      </td>
                      <td className="py-3 px-4 font-mono text-status-success">
                        {cust.successful_payment_count}
                      </td>
                      <td className="py-3 px-4 font-mono text-status-danger">
                        {cust.failed_payment_count}
                      </td>
                      <td className="py-3 px-4 text-right font-mono text-fg-muted">
                        {cust.last_payment_at ? formatRelativeTime(cust.last_payment_at) : "—"}
                      </td>
                    </tr>
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
                  className="p-1 rounded bg-surface border border-border disabled:opacity-40 hover:bg-surface-elevated text-fg-secondary"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  className="p-1 rounded bg-surface border border-border disabled:opacity-40 hover:bg-surface-elevated text-fg-secondary"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </>
        )}
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
            {/* Financial Totals */}
            <div className="p-4 rounded-lg bg-surface-subtle border border-border space-y-3">
              <span className="font-mono text-fg-muted uppercase tracking-wider text-[11px]">
                Lifetime Financial Overview
              </span>
              <div className="grid grid-cols-2 gap-4 pt-2">
                <div>
                  <span className="text-fg-muted font-mono">Total Paid</span>
                  <div className="text-lg font-bold font-mono text-status-success mt-0.5">
                    {formatINR(selectedCustomer.total_payment_amount)}
                  </div>
                </div>
                <div>
                  <span className="text-fg-muted font-mono">Total Transactions</span>
                  <div className="text-lg font-bold font-mono text-fg mt-0.5">
                    {selectedCustomer.successful_payment_count + selectedCustomer.failed_payment_count}
                  </div>
                </div>
              </div>
            </div>

            {/* Profile Info */}
            <div className="space-y-3">
              <h3 className="text-xs font-mono font-semibold text-fg-secondary uppercase tracking-wider">
                Identity & Contact
              </h3>
              <div className="p-4 rounded-lg bg-surface-subtle border border-border space-y-2 font-mono">
                <div className="flex justify-between">
                  <span className="text-fg-muted">Name:</span>
                  <span className="text-fg">{selectedCustomer.name || "N/A"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-fg-muted">Email:</span>
                  <span className="text-status-info">{selectedCustomer.email || "N/A"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-fg-muted">Phone:</span>
                  <span className="text-fg-secondary">{selectedCustomer.phone || "N/A"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-fg-muted">Razorpay Customer ID:</span>
                  <span className="text-fg-muted">{selectedCustomer.razorpay_customer_id || "None"}</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </DetailDrawer>
    </AppShell>
  );
}
