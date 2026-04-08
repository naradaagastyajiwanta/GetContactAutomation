import { useState } from "react";
import { Link } from "react-router-dom";
import { Users, Plus, Trash2, ChevronRight, Loader2 } from "lucide-react";
import { cn } from "../lib/utils";
import { Pagination } from "../components/ui/Pagination";
import {
  useMarketingGroups,
  useDeleteMarketingGroup,
} from "../hooks/useMarketing";
import { Button } from "../components/ui/Button";
import { Spinner } from "../components/ui/Spinner";
import { MarketingGenerateGroupModal } from "../components/marketing/MarketingGenerateGroupModal";
import { useAuth } from "../context/AuthContext";
import { formatDate } from "../lib/utils";
import {
  type MarketingGroup,
  type ClientType,
  CLIENT_TYPE_LABELS,
} from "../api/marketing";
import { usePageTour } from "../hooks/usePageTour";
import { MARKETING_GROUPS_TOUR_STEPS } from "../tours/marketing-groups.tour";

// ---------------------------------------------------------------------------
// Filter options
// ---------------------------------------------------------------------------
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
// Status config — gray · indigo · emerald only
// ---------------------------------------------------------------------------
const STATUS_CFG: Record<
  string,
  { dot: string; label: string; labelClass: string }
> = {
  draft: {
    dot: "bg-gray-300 dark:bg-gray-600",
    label: "Draft",
    labelClass: "text-gray-400 dark:text-gray-500",
  },
  searching: {
    dot: "bg-indigo-500 animate-pulse",
    label: "Searching",
    labelClass: "text-indigo-600 dark:text-indigo-400",
  },
  done: {
    dot: "bg-emerald-500",
    label: "Done",
    labelClass: "text-emerald-600 dark:text-emerald-400",
  },
};

// ---------------------------------------------------------------------------
// Group row card
// ---------------------------------------------------------------------------
function GroupCard({
  group,
  canManage,
  onDelete,
}: {
  group: MarketingGroup;
  canManage: boolean;
  onDelete: (id: number) => void;
}) {
  const cfg = STATUS_CFG[group.status] ?? STATUS_CFG.draft;
  const total = group.total_clients;
  const found = group.found_count;
  const notFound = group.not_found_count;
  const pending = Math.max(0, total - found - notFound);
  const foundPct = total > 0 ? (found / total) * 100 : 0;
  const notFoundPct = total > 0 ? (notFound / total) * 100 : 0;

  return (
    <div className="group relative overflow-hidden rounded-xl border border-gray-100 bg-white transition-colors hover:border-gray-200 hover:bg-gray-50/40 dark:border-gray-700/50 dark:bg-gray-800/40 dark:hover:border-gray-700 dark:hover:bg-gray-800/60">
      <Link
        to={`/marketing/groups/${group.id}`}
        className="flex items-center gap-4 px-4 py-3.5"
      >
        {/* Status dot */}
        <span
          className={cn(
            "mt-0.5 inline-block h-2 w-2 shrink-0 rounded-full",
            cfg.dot,
          )}
        />

        {/* Main info */}
        <div className="min-w-0 flex-1">
          {/* Name + type */}
          <div className="flex items-baseline gap-2">
            <p className="truncate text-sm font-medium text-gray-800 dark:text-gray-100">
              {group.name}
            </p>
            <span className="shrink-0 text-xs text-gray-400 dark:text-gray-500">
              {CLIENT_TYPE_LABELS[group.client_type] ?? group.client_type}
            </span>
          </div>

          {/* Stats + progress */}
          {total > 0 && (
            <div className="mt-1.5 flex items-center gap-3">
              {/* Mini progress bar */}
              <div className="h-1 w-24 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700/60">
                <div className="flex h-full">
                  {foundPct > 0 && (
                    <div
                      className="h-full bg-emerald-500 transition-all duration-500"
                      style={{ width: `${foundPct}%` }}
                    />
                  )}
                  {notFoundPct > 0 && (
                    <div
                      className="h-full bg-gray-300 dark:bg-gray-600 transition-all duration-500"
                      style={{ width: `${notFoundPct}%` }}
                    />
                  )}
                </div>
              </div>
              {/* Counts */}
              <span className="text-xs text-gray-400 dark:text-gray-500">
                <span className="text-emerald-600 dark:text-emerald-400">
                  {found}
                </span>
                <span className="mx-1 text-gray-200 dark:text-gray-700">/</span>
                <span>{total}</span>
                {pending > 0 && group.status === "searching" && (
                  <span className="ml-1 text-indigo-500 dark:text-indigo-400">
                    · {pending} pending
                  </span>
                )}
              </span>
            </div>
          )}

          {total === 0 && (
            <p className="mt-0.5 text-xs text-gray-400">Belum ada client</p>
          )}
        </div>

        {/* Right: status label + date + chevron */}
        <div className="flex shrink-0 items-center gap-4">
          <div className="hidden text-right sm:block">
            <p className={cn("text-xs font-medium", cfg.labelClass)}>
              {cfg.label}
              {group.status === "searching" && (
                <Loader2 className="ml-1 inline h-3 w-3 animate-spin" />
              )}
            </p>
            <p className="mt-0.5 text-[11px] text-gray-400 dark:text-gray-500">
              {formatDate(group.created_at)}
            </p>
          </div>
          <ChevronRight className="h-4 w-4 text-gray-300 dark:text-gray-600" />
        </div>
      </Link>

      {/* Delete — appears on hover, outside the Link */}
      {canManage && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete(group.id);
          }}
          className="absolute right-10 top-1/2 -translate-y-1/2 rounded p-1 text-gray-300 opacity-0 transition-all group-hover:opacity-100 hover:text-gray-600 dark:text-gray-600 dark:hover:text-gray-300"
          title="Hapus group"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function MarketingGetContactPage() {
  const { hasPermission } = useAuth();
  const [clientTypeFilter, setClientTypeFilter] = useState<ClientType | "">("");
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 50;
  const canManage = hasPermission("marketing.manage");

  usePageTour("marketing-groups", MARKETING_GROUPS_TOUR_STEPS);

  const { data, isLoading } = useMarketingGroups({
    ...(clientTypeFilter ? { client_type: clientTypeFilter } : {}),
    limit: pageSize,
    offset: (page - 1) * pageSize,
  });
  const deleteMutation = useDeleteMarketingGroup();

  const groups = data?.groups ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / pageSize);

  function handleDelete(groupId: number) {
    if (!window.confirm("Hapus group ini beserta seluruh client di dalamnya?"))
      return;
    deleteMutation.mutate(groupId);
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div
        data-tour="mktg-header"
        className="flex items-center justify-between border-b border-gray-100 pb-4 dark:border-gray-800"
      >
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-50 dark:bg-indigo-900/20">
            <Users className="h-4.5 w-4.5 text-indigo-600 dark:text-indigo-400" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Marketing
            </h1>
            <p className="text-xs text-gray-400 dark:text-gray-500">
              {total > 0 ? `${total} group` : "Kelola group client"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to="/marketing/clients"
            className="rounded-lg px-3 py-1.5 text-xs text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300"
          >
            Semua Client →
          </Link>
          {canManage && (
            <Button size="sm" onClick={() => setCreateModalOpen(true)}>
              <Plus className="h-3.5 w-3.5" />
              Buat Group
            </Button>
          )}
        </div>
      </div>

      {/* Filter */}
      <div data-tour="mktg-type-filter" className="flex items-center gap-2">
        <span className="text-xs text-gray-400">Tipe:</span>
        <div className="flex flex-wrap gap-1.5">
          {CLIENT_TYPE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => {
                setClientTypeFilter(opt.value as ClientType | "");
                setPage(1);
              }}
              className={cn(
                "rounded-lg px-2.5 py-1 text-xs transition-colors",
                clientTypeFilter === opt.value
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-100 text-gray-500 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700",
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="space-y-1.5">
          {Array.from({ length: 5 }).map((_, i) => (
            <div
              key={i}
              className="h-16 animate-pulse rounded-xl bg-gray-100 dark:bg-gray-800"
            />
          ))}
        </div>
      ) : groups.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-200 py-16 dark:border-gray-700">
          <Users className="mb-3 h-8 w-8 text-gray-200 dark:text-gray-700" />
          <p className="text-sm text-gray-400">
            {clientTypeFilter
              ? "Tidak ada group untuk tipe ini"
              : "Belum ada group"}
          </p>
          {canManage && !clientTypeFilter && (
            <button
              onClick={() => setCreateModalOpen(true)}
              className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
            >
              <Plus className="h-3.5 w-3.5" />
              Buat Group Pertama
            </button>
          )}
        </div>
      ) : (
        <div data-tour="mktg-group-list" className="space-y-1.5">
          {groups.map((g) => (
            <GroupCard
              key={g.id}
              group={g}
              canManage={canManage}
              onDelete={handleDelete}
            />
          ))}

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

      {createModalOpen && (
        <MarketingGenerateGroupModal
          onClose={() => setCreateModalOpen(false)}
        />
      )}
    </div>
  );
}
