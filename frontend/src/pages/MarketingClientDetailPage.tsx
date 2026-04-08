import { useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Play,
  Download,
  Upload,
  CheckCircle2,
  Plus,
  Loader2,
  Users,
  XCircle,
  Search,
  Brain,
  MoreHorizontal,
} from "lucide-react";
import { Pagination } from "../components/ui/Pagination";
import { cn } from "../lib/utils";
import {
  useMarketingGroupDetail,
  useMarketingClients,
  useStartGroupSearch,
  useSearchStatus,
  useBulkApproveGroupContacts,
  useExportGroupClients,
  useAddMarketingClient,
} from "../hooks/useMarketing";
import { Button } from "../components/ui/Button";
import { Spinner } from "../components/ui/Spinner";
import { MarketingImportModal } from "../components/marketing/MarketingImportModal";
import { MarketingClientResultsTable } from "../components/marketing/MarketingClientResultsTable";
import { MarketingReadyToBlastPanel } from "../components/marketing/MarketingReadyToBlastPanel";
import { useAuth } from "../context/AuthContext";
import { usePageTour } from "../hooks/usePageTour";
import { MARKETING_GROUP_DETAIL_TOUR_STEPS } from "../tours/marketing-group-detail.tour";
import { deleteMarketingGroup } from "../api/marketing";
import toast from "react-hot-toast";
import {
  type GroupStatus,
  CLIENT_TYPE_LABELS,
  getGroupStrategyMemo,
} from "../api/marketing";

// ---------------------------------------------------------------------------
// Status config — indigo for searching, emerald for done, gray for draft
// ---------------------------------------------------------------------------
const statusConfig: Record<
  GroupStatus,
  { label: string; dotClass: string; textClass: string }
> = {
  draft: {
    label: "Draft",
    dotClass: "bg-gray-300 dark:bg-gray-600",
    textClass: "text-gray-500 dark:text-gray-400",
  },
  searching: {
    label: "Searching",
    dotClass: "bg-indigo-500 animate-pulse",
    textClass: "text-indigo-600 dark:text-indigo-400",
  },
  done: {
    label: "Done",
    dotClass: "bg-emerald-500",
    textClass: "text-emerald-600 dark:text-emerald-400",
  },
};

// ---------------------------------------------------------------------------
// Processing animations
// ---------------------------------------------------------------------------

function BouncingDots({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-0.5", className)}>
      {[0, 150, 300].map((delay, i) => (
        <span
          key={i}
          className="inline-block h-1 w-1 animate-bounce rounded-full bg-indigo-500"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  );
}

function SearchingBanner({
  progress,
  total,
  activeCount,
}: {
  progress: number;
  total: number;
  activeCount: number;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-indigo-100 bg-indigo-50/60 px-4 py-2.5 dark:border-indigo-900/40 dark:bg-indigo-950/20">
      <BouncingDots />
      <p className="text-sm font-medium text-indigo-700 dark:text-indigo-300">
        AI agent sedang mencari kontak
      </p>
      {activeCount > 0 && (
        <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs text-indigo-600 dark:bg-indigo-900/40 dark:text-indigo-400">
          {activeCount} aktif
        </span>
      )}
      <span className="ml-auto shrink-0 text-xs tabular-nums text-indigo-400 dark:text-indigo-500">
        {progress}/{total}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Search progress bar — embedded inside stats strip
// ---------------------------------------------------------------------------
function SearchProgressBar({
  status,
  progress,
  total,
  found,
  not_found,
}: {
  status: GroupStatus;
  progress: number;
  total: number;
  found: number;
  not_found: number;
}) {
  if (status !== "searching") return null;
  const foundPct = total > 0 ? (found / total) * 100 : 0;
  const notFoundPct = total > 0 ? (not_found / total) * 100 : 0;
  const pendingPct = Math.max(0, 100 - foundPct - notFoundPct);
  const pct = total > 0 ? Math.round((progress / total) * 100) : 0;

  return (
    <div className="mt-3 space-y-1.5">
      {/* Thicker bar with shimmer on pending segment */}
      <div className="h-1.5 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700/60">
        <div className="flex h-full">
          {foundPct > 0 && (
            <div
              className="h-full bg-emerald-500 transition-all duration-700"
              style={{ width: `${foundPct}%` }}
            />
          )}
          {notFoundPct > 0 && (
            <div
              className="h-full bg-gray-300 dark:bg-gray-600 transition-all duration-700"
              style={{ width: `${notFoundPct}%` }}
            />
          )}
          {pendingPct > 0 && pct < 100 && (
            <div
              className="relative h-full overflow-hidden bg-indigo-100 dark:bg-indigo-900/40"
              style={{ width: `${pendingPct}%` }}
            >
              {/* Shimmer sweep on pending segment */}
              <div className="absolute inset-y-0 w-1/4 animate-shimmer bg-gradient-to-r from-transparent via-indigo-400/60 to-transparent dark:via-indigo-500/40" />
            </div>
          )}
        </div>
      </div>
      <div className="flex items-center justify-between text-[11px] text-gray-400">
        <span>
          {progress}/{total} diproses · {pct}%
        </span>
        <span className="flex gap-3">
          {found > 0 && (
            <span className="text-emerald-600 dark:text-emerald-400">
              {found} ditemukan
            </span>
          )}
          {not_found > 0 && <span>{not_found} tidak ditemukan</span>}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add client inline form
// ---------------------------------------------------------------------------
function AddClientInlineForm({
  groupId,
  onClose,
}: {
  groupId: number;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const addClient = useAddMarketingClient();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await addClient.mutateAsync({ groupId, name: name.trim() });
      toast.success("Client ditambahkan");
      setName("");
      onClose();
    } catch {
      toast.error("Gagal menambahkan client");
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2">
      <input
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Nama client..."
        className="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm
          focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500
          dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
      />
      <Button
        type="submit"
        size="sm"
        loading={addClient.isPending}
        disabled={!name.trim()}
      >
        Tambah
      </Button>
      <Button type="button" size="sm" variant="ghost" onClick={onClose}>
        Batal
      </Button>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function getGroupIgScrapeIncompleteCount(
  clients: Array<{
    search_status: string;
    ig_handle?: string | null;
    ig_posts?: unknown[];
  }>,
): number {
  return clients.filter(
    (client) =>
      client.search_status === "found" &&
      Boolean(client.ig_handle) &&
      (client.ig_posts?.length ?? 0) === 0,
  ).length;
}

// ---------------------------------------------------------------------------
// AI Group Memory panel
// ---------------------------------------------------------------------------
const TOOL_LABELS: Record<string, string> = {
  spawn_web_search_agent: "Web Search",
  spawn_instagram_agent: "Instagram",
  spawn_registry_agent: "Registry",
  spawn_gemini_agent: "Gemini",
};

function AgentBar({
  tool,
  produced,
  spawns,
}: {
  tool: string;
  produced: number;
  spawns: number;
}) {
  const rate = spawns > 0 ? Math.round((produced / spawns) * 100) : 0;
  const label =
    TOOL_LABELS[tool] ??
    tool.replace("spawn_", "").replace("_agent", "").replace(/_/g, " ");
  const barColor =
    rate >= 70
      ? "bg-emerald-500"
      : rate >= 40
        ? "bg-indigo-400"
        : "bg-gray-300 dark:bg-gray-600";

  return (
    <div className="flex items-center gap-3">
      <span className="w-24 shrink-0 text-xs capitalize text-gray-500 dark:text-gray-400">
        {label}
      </span>
      <div className="flex-1">
        <div className="h-1.5 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700/60">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-500",
              barColor,
            )}
            style={{ width: `${rate}%` }}
          />
        </div>
      </div>
      <span
        className={cn(
          "w-14 shrink-0 text-right text-xs tabular-nums",
          rate >= 70
            ? "text-emerald-600 dark:text-emerald-400"
            : rate >= 40
              ? "text-indigo-500 dark:text-indigo-400"
              : "text-gray-400",
        )}
      >
        {rate}%
        <span className="ml-1 text-gray-300 dark:text-gray-600">
          ({produced}/{spawns})
        </span>
      </span>
    </div>
  );
}

function GroupStrategyPanel({ groupId }: { groupId: number }) {
  const [isOpen, setIsOpen] = useState(false);
  const { data: strategy, isLoading } = useQuery({
    queryKey: ["groupStrategy", groupId],
    queryFn: () => getGroupStrategyMemo(groupId),
    enabled: isOpen,
    staleTime: 60_000,
  });

  const hitRate = Math.round((strategy?.found_rate ?? 0) * 100);
  const completedClients = strategy?.completed_clients ?? 0;

  // ── Collapsed ──
  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="group flex w-full items-center gap-2 rounded-xl border border-gray-100 bg-white px-4 py-2.5 text-left transition-colors hover:border-gray-200 hover:bg-gray-50 dark:border-gray-700/50 dark:bg-gray-800/40 dark:hover:bg-gray-800/60"
      >
        <Brain className="h-4 w-4 shrink-0 text-gray-400 group-hover:text-indigo-500 transition-colors" />
        <span className="text-sm text-gray-500 dark:text-gray-400 group-hover:text-gray-700 dark:group-hover:text-gray-200 transition-colors">
          AI Memory
        </span>
        {completedClients > 0 && (
          <>
            <span className="text-gray-200 dark:text-gray-700">·</span>
            <span className="text-xs text-gray-400">
              {completedClients} run
            </span>
            <span className="text-gray-200 dark:text-gray-700">·</span>
            <span
              className={cn(
                "text-xs font-medium",
                hitRate >= 70
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-gray-400",
              )}
            >
              {hitRate}% hit rate
            </span>
          </>
        )}
        <span className="ml-auto text-xs text-gray-300 dark:text-gray-600 group-hover:text-gray-400">
          Lihat detail ↓
        </span>
      </button>
    );
  }

  const hasAgentRates =
    strategy && Object.keys(strategy.tool_success_rates).length > 0;
  const hasLessons = strategy && strategy.lessons.length > 0;
  const hasData =
    strategy && (hasAgentRates || hasLessons || completedClients > 0);

  // ── Expanded ──
  return (
    <div className="overflow-hidden rounded-xl border border-gray-100 bg-white dark:border-gray-700/50 dark:bg-gray-800/40">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3 dark:border-gray-700/50">
        <div className="flex items-center gap-2">
          <Brain className="h-4 w-4 text-indigo-500" />
          <span className="text-sm font-medium text-gray-700 dark:text-gray-200">
            AI Memory
          </span>
          {strategy && (
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <span className="text-gray-200 dark:text-gray-700">·</span>
              <span>{completedClients} run selesai</span>
              <span className="text-gray-200 dark:text-gray-700">·</span>
              <span
                className={
                  hitRate >= 70
                    ? "font-medium text-emerald-600 dark:text-emerald-400"
                    : "text-gray-400"
                }
              >
                {hitRate}% hit rate
              </span>
            </div>
          )}
        </div>
        <button
          onClick={() => setIsOpen(false)}
          className="text-xs text-gray-400 transition-colors hover:text-gray-600 dark:hover:text-gray-300"
        >
          Tutup
        </button>
      </div>

      {/* Body */}
      <div className="p-4">
        {isLoading && (
          <div className="space-y-2">
            {[80, 60, 70].map((w, i) => (
              <div
                key={i}
                className="h-3 animate-pulse rounded bg-gray-100 dark:bg-gray-700"
                style={{ width: `${w}%` }}
              />
            ))}
          </div>
        )}

        {!isLoading && !hasData && (
          <p className="text-xs text-gray-400">
            Belum ada AI memory — akan terisi setelah pencarian pertama selesai.
          </p>
        )}

        {!isLoading && hasData && (
          <div className="space-y-5">
            {/* Agent success rates */}
            {hasAgentRates && (
              <div>
                <p className="mb-2.5 text-[11px] font-medium uppercase tracking-wide text-gray-400">
                  Agent Success Rates
                </p>
                <div className="space-y-2">
                  {Object.entries(strategy.tool_success_rates).map(
                    ([tool, stats]) => (
                      <AgentBar
                        key={tool}
                        tool={tool}
                        produced={stats.produced_contacts}
                        spawns={stats.spawns}
                      />
                    ),
                  )}
                </div>
              </div>
            )}

            {/* Lessons */}
            {hasLessons && (
              <div>
                <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-gray-400">
                  Recent Lessons
                </p>
                <div className="space-y-1.5">
                  {strategy.lessons.slice(0, 4).map((lesson, i) => {
                    const text =
                      typeof lesson === "string"
                        ? lesson
                        : ((lesson as { summary?: string }).summary ?? "");
                    const status =
                      typeof lesson === "object"
                        ? (lesson as { status?: string }).status
                        : null;
                    return (
                      <div
                        key={i}
                        className="flex gap-2.5 rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-700/30"
                      >
                        <span
                          className={cn(
                            "mt-0.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full",
                            status === "found"
                              ? "bg-emerald-500"
                              : status === "partial"
                                ? "bg-emerald-300"
                                : "bg-gray-300 dark:bg-gray-600",
                          )}
                        />
                        <p className="line-clamp-2 text-xs leading-relaxed text-gray-500 dark:text-gray-400">
                          {text}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function MarketingClientDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { hasPermission } = useAuth();
  const navigate = useNavigate();
  const groupId = Number(id);
  const queryClient = useQueryClient();

  const [importOpen, setImportOpen] = useState(false);
  const [addClientOpen, setAddClientOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchStatusFilter, setSearchStatusFilter] = useState("");
  const pageSize = 50;

  const { data, isLoading, error } = useMarketingGroupDetail(groupId);
  const { data: clientsData } = useMarketingClients(groupId, {
    limit: pageSize,
    offset: (page - 1) * pageSize,
    q: searchQuery || undefined,
    search_status: searchStatusFilter || undefined,
  });
  const canManage = hasPermission("marketing.manage");
  const isDummyGroup =
    localStorage.getItem("onboarding_dummy_group_id") === String(groupId);
  usePageTour("marketing-group-detail", MARKETING_GROUP_DETAIL_TOUR_STEPS, {
    onComplete: async () => {
      const dummyId = localStorage.getItem("onboarding_dummy_group_id");
      if (dummyId && Number(dummyId) === groupId) {
        try {
          await deleteMarketingGroup(groupId);
        } catch {
          // best-effort
        }
        localStorage.removeItem("onboarding_dummy_group_id");
        navigate("/marketing");
      }
    },
  });

  const group = data?.group;
  const stats = data?.stats;
  const clients = clientsData?.clients ?? [];
  const totalClients = clientsData?.total ?? 0;
  const totalPages = Math.ceil(totalClients / pageSize);
  const igScrapeIncompleteCount = getGroupIgScrapeIncompleteCount(clients);

  const searchStatusEnabled = group?.status === "searching";
  const { data: searchStatus } = useSearchStatus(groupId, searchStatusEnabled);

  const startSearchMutation = useStartGroupSearch();
  const bulkApproveMutation = useBulkApproveGroupContacts();
  const exportMutation = useExportGroupClients();

  const statusCfg = statusConfig[group?.status ?? "draft"];
  const showDoneWarning =
    group?.status === "done" && igScrapeIncompleteCount > 0;
  const isSearching =
    searchStatus?.status === "searching" || group?.status === "searching";

  useEffect(() => {
    if (searchStatus?.status !== "done") return;
    void queryClient.invalidateQueries({
      queryKey: ["marketing", "clients", groupId],
    });
    void queryClient.invalidateQueries({
      queryKey: ["marketing", "group", groupId],
    });
  }, [groupId, queryClient, searchStatus]);

  async function handleStartSearch() {
    try {
      await startSearchMutation.mutateAsync(groupId);
      toast.success("Scraping dimulai");
    } catch {
      toast.error("Gagal memulai scraping");
    }
  }

  async function handleBulkApprove() {
    if (!window.confirm("Approve semua kontak yang ditemukan?")) return;
    try {
      const result = await bulkApproveMutation.mutateAsync(groupId);
      toast.success(`${result.approved} kontak di-approve`);
    } catch {
      toast.error("Gagal bulk approve");
    }
  }

  async function handleExport() {
    try {
      const blob = await exportMutation.mutateAsync(groupId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${group?.name ?? "marketing-group"}-export.xlsx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Gagal export data");
    }
  }

  // ── Loading skeleton ──
  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 animate-pulse rounded-lg bg-gray-100 dark:bg-gray-800" />
          <div className="space-y-2">
            <div className="h-5 w-44 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
            <div className="h-3.5 w-28 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
          </div>
        </div>
        <div className="h-20 animate-pulse rounded-xl bg-gray-100 dark:bg-gray-800" />
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="h-14 animate-pulse rounded-xl bg-gray-100 dark:bg-gray-800"
            />
          ))}
        </div>
      </div>
    );
  }

  // ── Error state ──
  if (error || !group) {
    return (
      <div className="space-y-4">
        <Link
          to="/marketing"
          className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
        >
          <ArrowLeft className="h-4 w-4" /> Kembali
        </Link>
        <p className="text-sm text-gray-500">
          Gagal memuat data group:{" "}
          {(error as Error)?.message ?? "Unknown error"}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* ── Dummy onboarding banner ── */}
      {isDummyGroup && (
        <div className="flex items-center gap-3 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 dark:border-indigo-800/50 dark:bg-indigo-950/30">
          <span className="text-lg">🎓</span>
          <div className="flex-1">
            <p className="text-sm font-medium text-indigo-800 dark:text-indigo-200">
              Grup Demo Onboarding
            </p>
            <p className="text-xs text-indigo-600 dark:text-indigo-400">
              Ini adalah grup latihan — scraping tidak akan dijalankan. Grup ini
              akan otomatis dihapus setelah kamu selesai tour.
            </p>
          </div>
        </div>
      )}

      {/* ── Header ── */}
      <div
        data-tour="group-detail-header"
        className="flex items-start justify-between gap-4 pb-4 border-b border-gray-100 dark:border-gray-800"
      >
        <div className="flex items-start gap-3">
          <Link
            to="/marketing"
            className="mt-0.5 rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div>
            <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              {group.name}
            </h1>
            <div className="mt-1 flex items-center gap-2.5 text-xs">
              {/* Status dot + label */}
              <span className="flex items-center gap-1.5">
                <span className="relative inline-flex h-1.5 w-1.5 shrink-0">
                  {isSearching && (
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-75" />
                  )}
                  <span
                    className={cn(
                      "relative inline-block h-1.5 w-1.5 rounded-full",
                      showDoneWarning
                        ? "bg-gray-400 dark:bg-gray-500"
                        : statusCfg.dotClass,
                    )}
                  />
                </span>
                <span
                  className={
                    showDoneWarning
                      ? "text-gray-500 dark:text-gray-400"
                      : statusCfg.textClass
                  }
                >
                  {showDoneWarning ? "Done (IG incomplete)" : statusCfg.label}
                </span>
              </span>
              <span className="text-gray-200 dark:text-gray-700">·</span>
              <span className="text-gray-400">
                {CLIENT_TYPE_LABELS[group.client_type] ?? group.client_type}
              </span>
              <span className="text-gray-200 dark:text-gray-700">·</span>
              <span className="text-gray-400">
                {formatDate(group.created_at)}
              </span>
            </div>
          </div>
        </div>

        {/* Action buttons */}
        {canManage && (
          <div
            data-tour="group-detail-actions"
            className="flex items-center gap-2"
          >
            {group.status !== "searching" && (
              <Button
                size="sm"
                onClick={handleStartSearch}
                loading={startSearchMutation.isPending}
                disabled={isDummyGroup}
                title={isDummyGroup ? "Tidak tersedia di grup demo" : undefined}
              >
                <Play className="h-3.5 w-3.5" />
                Mulai Scraping
              </Button>
            )}
            {/* More dropdown */}
            <div className="relative">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setMoreOpen((o) => !o)}
              >
                <MoreHorizontal className="h-4 w-4" />
              </Button>
              {moreOpen && (
                <>
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setMoreOpen(false)}
                  />
                  <div className="absolute right-0 top-full z-20 mt-1 w-48 overflow-hidden rounded-xl border border-gray-100 bg-white shadow-lg dark:border-gray-700/60 dark:bg-gray-800">
                    <button
                      className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-40 dark:text-gray-300 dark:hover:bg-gray-700/40"
                      onClick={() => {
                        void handleBulkApprove();
                        setMoreOpen(false);
                      }}
                      disabled={
                        bulkApproveMutation.isPending ||
                        clients.flatMap((c) => c.contacts ?? []).length === 0
                      }
                    >
                      <CheckCircle2 className="h-3.5 w-3.5 text-gray-400" />
                      Approve Semua
                    </button>
                    <button
                      className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-40 dark:text-gray-300 dark:hover:bg-gray-700/40"
                      onClick={() => {
                        void handleExport();
                        setMoreOpen(false);
                      }}
                      disabled={
                        exportMutation.isPending || clients.length === 0
                      }
                    >
                      <Download className="h-3.5 w-3.5 text-gray-400" />
                      Export Excel
                    </button>
                    <button
                      className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-700/40"
                      onClick={() => {
                        setImportOpen(true);
                        setMoreOpen(false);
                      }}
                    >
                      <Upload className="h-3.5 w-3.5 text-gray-400" />
                      Upload Excel
                    </button>
                    <div className="mx-3 my-1 border-t border-gray-100 dark:border-gray-700/50" />
                    <button
                      className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-700/40"
                      onClick={() => {
                        setAddClientOpen(true);
                        setMoreOpen(false);
                      }}
                    >
                      <Plus className="h-3.5 w-3.5 text-gray-400" />
                      Tambah Client
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ── Searching banner ── */}
      {isSearching && searchStatus && (
        <SearchingBanner
          progress={searchStatus.progress}
          total={searchStatus.total}
          activeCount={
            clients.filter((c) => c.search_status === "searching").length
          }
        />
      )}

      {/* ── Stats strip ── */}
      {stats && (
        <div
          data-tour="group-detail-stats"
          className="overflow-hidden rounded-xl border border-gray-100 bg-white shadow-sm dark:border-gray-700/50 dark:bg-gray-800/60"
        >
          <div className="grid grid-cols-4 divide-x divide-gray-100 dark:divide-gray-700/50">
            {/* Total */}
            <div className="px-5 py-4">
              <p className="text-[11px] font-medium uppercase tracking-wide text-gray-400">
                Total
              </p>
              <p className="mt-1 text-2xl font-semibold text-gray-800 dark:text-gray-100">
                {stats.total}
              </p>
            </div>
            {/* Ditemukan */}
            <div className="px-5 py-4">
              <p className="text-[11px] font-medium uppercase tracking-wide text-gray-400">
                Ditemukan
              </p>
              <p className="mt-1 text-2xl font-semibold text-emerald-600 dark:text-emerald-400">
                {stats.found}
              </p>
              {(stats.partial > 0 ||
                stats.not_found > 0 ||
                stats.error_count > 0) && (
                <p className="mt-0.5 text-[11px] leading-snug text-gray-400">
                  {[
                    stats.partial > 0 && `${stats.partial} partial`,
                    stats.not_found > 0 && `${stats.not_found} tdk ditemukan`,
                    stats.error_count > 0 && `${stats.error_count} error`,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              )}
            </div>
            {/* Pending */}
            <div className="px-5 py-4">
              <p className="text-[11px] font-medium uppercase tracking-wide text-gray-400">
                Pending
              </p>
              <p className="mt-1 text-2xl font-semibold text-gray-600 dark:text-gray-300">
                {stats.pending}
              </p>
            </div>
            {/* Approved */}
            <div className="px-5 py-4">
              <p className="text-[11px] font-medium uppercase tracking-wide text-gray-400">
                Approved
              </p>
              <p className="mt-1 text-2xl font-semibold text-indigo-600 dark:text-indigo-400">
                {stats.approved}
              </p>
            </div>
          </div>

          {/* Progress bar embedded in strip */}
          {isSearching && searchStatus && (
            <div className="border-t border-gray-100 px-5 py-3 dark:border-gray-700/50">
              <SearchProgressBar
                status={searchStatus.status}
                progress={searchStatus.progress}
                total={searchStatus.total}
                found={searchStatus.found}
                not_found={searchStatus.not_found}
              />
              {searchStatus.error_message && (
                <p className="mt-1.5 text-xs text-gray-500">
                  {searchStatus.error_message}
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Alert banners — no colored cards, just left-border lines ── */}
      {searchStatus?.group_search_error && (
        <div className="flex items-start gap-3 rounded-r-lg border-l-2 border-gray-400 bg-gray-50 px-4 py-3 dark:bg-gray-800/40">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-gray-500" />
          <div>
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Scraping gagal
            </p>
            <p className="mt-0.5 text-xs text-gray-500">
              {searchStatus.group_search_error}
            </p>
          </div>
        </div>
      )}

      {showDoneWarning && (
        <div className="flex items-start gap-3 rounded-r-lg border-l-2 border-gray-300 bg-gray-50 px-4 py-3 dark:bg-gray-800/40">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-gray-400" />
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {igScrapeIncompleteCount} client sudah punya handle IG, tapi belum
            ada post tersimpan — provider scrape tidak mengembalikan data.
          </p>
        </div>
      )}

      {/* ── Ready to blast panel ── */}
      <MarketingReadyToBlastPanel clients={clients} groupId={groupId} />

      {/* ── Add client form ── */}
      {addClientOpen && (
        <div className="rounded-xl border border-gray-100 bg-white p-4 dark:border-gray-700/50 dark:bg-gray-800/60">
          <p className="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">
            Tambah Client Baru
          </p>
          <AddClientInlineForm
            groupId={groupId}
            onClose={() => setAddClientOpen(false)}
          />
        </div>
      )}

      {/* ── AI Group Memory ── */}
      <GroupStrategyPanel groupId={groupId} />

      {/* ── Client list ── */}
      <div data-tour="group-detail-clients">
        {/* Header row */}
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm font-medium text-gray-600 dark:text-gray-400">
            {totalClients} client
            {(searchQuery || searchStatusFilter) && (
              <span className="ml-1 text-gray-400">— hasil filter</span>
            )}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-300 dark:text-gray-600" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setPage(1);
                }}
                placeholder="Cari client..."
                className="h-8 w-44 rounded-lg border border-gray-200 bg-white pl-8 pr-3 text-sm text-gray-700
                  placeholder:text-gray-300 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500
                  dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:placeholder:text-gray-600"
              />
            </div>
            <select
              value={searchStatusFilter}
              onChange={(e) => {
                setSearchStatusFilter(e.target.value);
                setPage(1);
              }}
              className="h-8 rounded-lg border border-gray-200 bg-white px-2.5 text-sm text-gray-600
                focus:border-indigo-500 focus:outline-none
                dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
            >
              <option value="">Semua Status</option>
              <option value="pending">Pending</option>
              <option value="searching">Searching</option>
              <option value="found">Ditemukan</option>
              <option value="partial">Partial</option>
              <option value="not_found">Tidak Ditemukan</option>
              <option value="error">Error</option>
            </select>
          </div>
        </div>

        {/* Empty state */}
        {clients.length === 0 && (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-200 py-14 text-center dark:border-gray-700">
            <Users className="mb-3 h-8 w-8 text-gray-200 dark:text-gray-700" />
            <p className="text-sm text-gray-400">
              {searchQuery || searchStatusFilter
                ? "Tidak ada client yang cocok dengan filter"
                : "Belum ada client di group ini"}
            </p>
            {canManage && !searchQuery && !searchStatusFilter && (
              <button
                onClick={() => setAddClientOpen(true)}
                className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
              >
                <Plus className="h-3.5 w-3.5" />
                Tambah Client Pertama
              </button>
            )}
          </div>
        )}

        {/* Client table */}
        {clients.length > 0 && (
          <>
            <MarketingClientResultsTable
              clients={clients}
              groupId={groupId}
              canManage={canManage}
            />
            {totalPages > 1 && (
              <div className="mt-4 flex items-center justify-between">
                <p className="text-xs text-gray-400">
                  {(page - 1) * pageSize + 1}–
                  {Math.min(page * pageSize, totalClients)} dari {totalClients}
                </p>
                <Pagination
                  currentPage={page}
                  totalPages={totalPages}
                  onPageChange={(p) => setPage(p)}
                />
              </div>
            )}
          </>
        )}
      </div>

      {/* Import modal */}
      {importOpen && (
        <MarketingImportModal
          groupId={groupId}
          onClose={() => setImportOpen(false)}
        />
      )}
    </div>
  );
}

function formatDate(date: string | null): string {
  if (!date) return "-";
  return new Intl.DateTimeFormat("id-ID", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(date));
}
