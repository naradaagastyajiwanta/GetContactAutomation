import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  ChevronRight,
  Search,
  Users,
  Wifi,
  Mail,
} from "lucide-react";
import { cn } from "../lib/utils";
import { Pagination } from "../components/ui/Pagination";
import { useAllMarketingClients } from "../hooks/useMarketing";
import { formatDate } from "../lib/utils";
import { CLIENT_TYPE_LABELS, type ClientType } from "../api/marketing";

// ---------------------------------------------------------------------------
// Status dot config — gray · indigo · emerald
// ---------------------------------------------------------------------------
const STATUS_CFG: Record<
  string,
  { dot: string; label: string; labelClass: string }
> = {
  found: {
    dot: "bg-emerald-500",
    label: "Found",
    labelClass: "text-emerald-600 dark:text-emerald-400",
  },
  partial: {
    dot: "bg-emerald-300",
    label: "Partial",
    labelClass: "text-emerald-600 dark:text-emerald-400",
  },
  searching: {
    dot: "bg-indigo-500 animate-pulse",
    label: "Searching",
    labelClass: "text-indigo-600 dark:text-indigo-400",
  },
  pending: {
    dot: "bg-gray-300 dark:bg-gray-600",
    label: "Pending",
    labelClass: "text-gray-400 dark:text-gray-500",
  },
  not_found: {
    dot: "bg-gray-300 dark:bg-gray-600",
    label: "—",
    labelClass: "text-gray-400 dark:text-gray-500",
  },
  error: {
    dot: "bg-gray-500",
    label: "Error",
    labelClass: "text-gray-500 dark:text-gray-400",
  },
};

const STATUS_FILTERS = [
  { value: "", label: "Semua" },
  { value: "found", label: "Found" },
  { value: "partial", label: "Partial" },
  { value: "pending", label: "Pending" },
  { value: "not_found", label: "Tidak Ditemukan" },
  { value: "error", label: "Error" },
];

const CLIENT_TYPE_OPTIONS: { value: ClientType | ""; label: string }[] = [
  { value: "", label: "Semua Tipe" },
  { value: "lembaga_negara", label: "Lembaga Negara" },
  { value: "kementerian", label: "Kementerian" },
  { value: "bumn", label: "BUMN" },
  { value: "swasta_besar", label: "Swasta Besar" },
  { value: "asosiasi", label: "Asosiasi" },
  { value: "lpk", label: "LPK" },
  { value: "lkp", label: "LKP" },
  { value: "lsp_p1", label: "LSP P1" },
  { value: "lsp_p2", label: "LSP P2" },
  { value: "lsp_p3", label: "LSP P3" },
  { value: "dinas", label: "Dinas" },
];

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function MarketingClientsPage() {
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [clientTypeFilter, setClientTypeFilter] = useState<ClientType | "">("");
  const [hasContactOnly, setHasContactOnly] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const { data, isLoading } = useAllMarketingClients({
    limit: pageSize,
    offset: (page - 1) * pageSize,
    q: q || undefined,
    search_status: statusFilter || undefined,
    client_type: clientTypeFilter || undefined,
    has_contact: hasContactOnly ? true : undefined,
  });

  const clients = data?.clients ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / pageSize);

  function resetPage() {
    setPage(1);
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 pb-4 dark:border-gray-800">
        <div className="flex items-center gap-3">
          <Link
            to="/marketing"
            className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-50 dark:bg-indigo-900/20">
            <Users className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Semua Client
            </h1>
            <p className="text-xs text-gray-400 dark:text-gray-500">
              {total > 0
                ? `${total} client di semua group`
                : "Lintas semua group"}
            </p>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="space-y-2.5">
        {/* Search input */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-300 dark:text-gray-600" />
          <input
            type="text"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              resetPage();
            }}
            placeholder="Cari nama client..."
            className="h-9 w-full rounded-xl border border-gray-200 bg-white pl-9 pr-4 text-sm text-gray-700
              placeholder:text-gray-300 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500
              dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:placeholder:text-gray-600"
          />
        </div>

        {/* Status pill filters */}
        <div className="flex flex-wrap items-center gap-1.5">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => {
                setStatusFilter(f.value);
                resetPage();
              }}
              className={cn(
                "rounded-lg px-2.5 py-1 text-xs transition-colors",
                statusFilter === f.value
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-100 text-gray-500 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700",
              )}
            >
              {f.label}
            </button>
          ))}

          <span className="mx-1 text-gray-200 dark:text-gray-700">|</span>

          {/* Client type dropdown */}
          <select
            value={clientTypeFilter}
            onChange={(e) => {
              setClientTypeFilter(e.target.value as ClientType | "");
              resetPage();
            }}
            className="h-7 rounded-lg border border-gray-200 bg-white px-2 text-xs text-gray-600
              focus:border-indigo-500 focus:outline-none
              dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
          >
            {CLIENT_TYPE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>

          {/* Has contact toggle */}
          <button
            onClick={() => {
              setHasContactOnly((v) => !v);
              resetPage();
            }}
            className={cn(
              "rounded-lg px-2.5 py-1 text-xs transition-colors",
              hasContactOnly
                ? "bg-emerald-600 text-white"
                : "bg-gray-100 text-gray-500 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700",
            )}
          >
            Punya Kontak
          </button>
        </div>
      </div>

      {/* List */}
      {isLoading ? (
        <div className="space-y-1.5">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              className="h-14 animate-pulse rounded-xl bg-gray-100 dark:bg-gray-800"
              style={{ opacity: 1 - i * 0.1 }}
            />
          ))}
        </div>
      ) : clients.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-200 py-16 dark:border-gray-700">
          <Users className="mb-3 h-8 w-8 text-gray-200 dark:text-gray-700" />
          <p className="text-sm text-gray-400">
            {q || statusFilter || clientTypeFilter || hasContactOnly
              ? "Tidak ada client yang cocok dengan filter"
              : "Belum ada client"}
          </p>
        </div>
      ) : (
        <div className="space-y-1.5">
          {/* Column hints */}
          <div className="flex items-center gap-4 px-4 pb-1 text-[11px] font-medium uppercase tracking-wide text-gray-300 dark:text-gray-600">
            <span className="flex-1">Client</span>
            <span className="hidden w-36 sm:block">Group</span>
            <span className="w-20 text-right">Kontak</span>
            <span className="w-16 text-right">Status</span>
            <span className="w-4" />
          </div>

          {clients.map((client) => {
            const cfg = STATUS_CFG[client.search_status] ?? STATUS_CFG.pending;
            const hasContacts = client.wa_count > 0 || client.email_count > 0;

            return (
              <div
                key={client.id}
                className="group relative overflow-hidden rounded-xl border border-gray-100 bg-white transition-colors hover:border-gray-200 hover:bg-gray-50/40 dark:border-gray-700/50 dark:bg-gray-800/40 dark:hover:bg-gray-800/60"
              >
                <Link
                  to={`/marketing/clients/${client.id}`}
                  className="flex items-center gap-4 px-4 py-3"
                >
                  {/* Status dot */}
                  <span
                    className={cn(
                      "mt-0.5 inline-block h-2 w-2 shrink-0 rounded-full",
                      cfg.dot,
                    )}
                  />

                  {/* Name + group */}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-gray-800 dark:text-gray-100">
                      {client.name}
                    </p>
                    <div className="mt-0.5 flex items-center gap-1.5 text-xs text-gray-400 dark:text-gray-500">
                      <Link
                        to={`/marketing/groups/${client.group_id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="truncate hover:text-indigo-500 dark:hover:text-indigo-400 transition-colors"
                      >
                        {client.group_name}
                      </Link>
                      <span className="text-gray-200 dark:text-gray-700">
                        ·
                      </span>
                      <span className="shrink-0">
                        {CLIENT_TYPE_LABELS[client.client_type as ClientType] ??
                          client.client_type}
                      </span>
                    </div>
                  </div>

                  {/* Contact counts */}
                  <div className="flex w-20 shrink-0 items-center justify-end gap-2 text-xs">
                    {hasContacts ? (
                      <>
                        {client.wa_count > 0 && (
                          <span className="flex items-center gap-0.5 text-emerald-600 dark:text-emerald-400">
                            <Wifi className="h-3 w-3" />
                            {client.wa_count}
                          </span>
                        )}
                        {client.email_count > 0 && (
                          <span className="flex items-center gap-0.5 text-indigo-500 dark:text-indigo-400">
                            <Mail className="h-3 w-3" />
                            {client.email_count}
                          </span>
                        )}
                      </>
                    ) : (
                      <span className="text-gray-300 dark:text-gray-600">
                        —
                      </span>
                    )}
                  </div>

                  {/* Status label */}
                  <div className="w-16 shrink-0 text-right">
                    <span className={cn("text-xs", cfg.labelClass)}>
                      {cfg.label}
                    </span>
                  </div>

                  <ChevronRight className="h-4 w-4 shrink-0 text-gray-300 dark:text-gray-600" />
                </Link>
              </div>
            );
          })}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-2">
              <p className="text-xs text-gray-400">
                {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)}{" "}
                dari {total}
              </p>
              <Pagination
                currentPage={page}
                totalPages={totalPages}
                onPageChange={(p) => setPage(p)}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
