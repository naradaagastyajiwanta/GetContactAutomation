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
  Wifi,
  Mail,
  Phone,
  User,
  Briefcase,
  XCircle,
  Search,
  Brain,
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
import { Card, CardHeader, CardTitle } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Spinner } from "../components/ui/Spinner";
import { Badge } from "../components/ui/Badge";
import { Modal } from "../components/ui/Modal";
import { MarketingImportModal } from "../components/marketing/MarketingImportModal";
import { MarketingClientResultsTable } from "../components/marketing/MarketingClientResultsTable";
import { MarketingReadyToBlastPanel } from "../components/marketing/MarketingReadyToBlastPanel";
import { useAuth } from "../context/AuthContext";
import toast from "react-hot-toast";
import {
  type GroupStatus,
  CLIENT_TYPE_LABELS,
  getGroupStrategyMemo,
  type GroupStrategyMemo,
} from "../api/marketing";

const statusConfig: Record<
  GroupStatus,
  { label: string; color: string; bg: string; icon: React.ElementType }
> = {
  draft: {
    label: "Draft",
    color: "text-gray-600 dark:text-gray-400",
    bg: "bg-gray-100 dark:bg-gray-800",
    icon: XCircle,
  },
  searching: {
    label: "Searching",
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-50 dark:bg-blue-900/30",
    icon: Loader2,
  },
  done: {
    label: "Done",
    color: "text-green-600 dark:text-green-400",
    bg: "bg-green-50 dark:bg-green-900/30",
    icon: CheckCircle2,
  },
};

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
  const pct = total > 0 ? Math.round((progress / total) * 100) : 0;
  const foundPct = total > 0 ? (found / total) * 100 : 0;
  const notFoundPct = total > 0 ? (not_found / total) * 100 : 0;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
        <span>
          {progress}/{total} diproses
        </span>
        <span>{pct}%</span>
      </div>
      <div className="h-2.5 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700">
        <div className="flex h-full">
          {foundPct > 0 && (
            <div
              className="h-full bg-green-500 transition-all duration-500"
              style={{ width: `${foundPct}%` }}
            />
          )}
          {notFoundPct > 0 && (
            <div
              className="h-full bg-red-400 transition-all duration-500"
              style={{ width: `${notFoundPct}%` }}
            />
          )}
          {pct < 100 && (
            <div
              className="h-full bg-blue-400 animate-pulse"
              style={{ width: `${Math.max(0, 100 - foundPct - notFoundPct)}%` }}
            />
          )}
        </div>
      </div>
      <div className="flex gap-4 text-xs">
        <span className="text-green-600 dark:text-green-400">
          {found} ditemukan
        </span>
        <span className="text-red-500">{not_found} tidak ditemukan</span>
      </div>
    </div>
  );
}

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
        className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm
          focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500
          dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
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

function GroupStrategyPanel({ groupId }: { groupId: number }) {
  const [isOpen, setIsOpen] = useState(false);
  const { data: strategy, isLoading } = useQuery({
    queryKey: ["groupStrategy", groupId],
    queryFn: () => getGroupStrategyMemo(groupId),
    enabled: isOpen,
    staleTime: 60_000,
  });

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="flex items-center gap-1.5 text-xs text-purple-600 dark:text-purple-400 hover:underline"
      >
        <Brain className="h-3.5 w-3.5" />
        <span>Lihat AI Group Memory</span>
      </button>
    );
  }

  const hasData =
    strategy && (strategy.lessons.length > 0 || strategy.completed_clients > 0);

  return (
    <div className="rounded-lg border border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-950/30 p-4 mb-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Brain className="h-4 w-4 text-purple-600 dark:text-purple-400" />
          <span className="text-sm font-semibold text-purple-700 dark:text-purple-300">
            AI Group Memory
          </span>
          {strategy && (
            <span className="text-xs text-purple-500">
              {strategy.completed_clients} klien selesai · hit rate{" "}
              {Math.round((strategy.found_rate ?? 0) * 100)}%
            </span>
          )}
        </div>
        <button
          onClick={() => setIsOpen(false)}
          className="text-xs text-gray-400 hover:text-gray-600"
        >
          Tutup
        </button>
      </div>

      {isLoading && <p className="text-xs text-gray-400">Memuat...</p>}

      {!isLoading && !hasData && (
        <p className="text-xs text-gray-400">
          Belum ada AI memory untuk grup ini (mulai setelah pencarian pertama
          selesai).
        </p>
      )}

      {hasData && (
        <div className="space-y-3">
          {/* Lessons */}
          {strategy.lessons.length > 0 && (
            <div>
              <p className="text-xs font-medium text-purple-600 dark:text-purple-400 mb-1">
                Lessons:
              </p>
              <ul className="space-y-1">
                {strategy.lessons.slice(0, 3).map((lesson, i) => (
                  <li
                    key={i}
                    className="text-xs text-gray-600 dark:text-gray-400 flex gap-1.5"
                  >
                    <span className="text-purple-400 flex-shrink-0">•</span>
                    <span className="line-clamp-2">{lesson}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Tool success rates */}
          {Object.keys(strategy.tool_success_rates).length > 0 && (
            <div>
              <p className="text-xs font-medium text-purple-600 dark:text-purple-400 mb-1">
                Agent Success Rates:
              </p>
              <div className="grid grid-cols-2 gap-1">
                {Object.entries(strategy.tool_success_rates).map(
                  ([tool, stats]) => {
                    const rate =
                      stats.spawns > 0
                        ? Math.round(
                            (stats.produced_contacts / stats.spawns) * 100,
                          )
                        : 0;
                    const label = tool
                      .replace("spawn_", "")
                      .replace("_agent", "")
                      .replace("_", " ");
                    return (
                      <div
                        key={tool}
                        className="text-xs text-gray-600 dark:text-gray-400"
                      >
                        <span className="capitalize">{label}</span>:{" "}
                        <span
                          className={
                            rate > 50 ? "text-green-500" : "text-gray-400"
                          }
                        >
                          {stats.produced_contacts}/{stats.spawns}
                        </span>
                      </div>
                    );
                  },
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function MarketingClientDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { hasPermission } = useAuth();
  const groupId = Number(id);
  const queryClient = useQueryClient();

  const [importOpen, setImportOpen] = useState(false);
  const [addClientOpen, setAddClientOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchStatusFilter, setSearchStatusFilter] = useState("");
  const pageSize = 50;

  const { data, isLoading, error } = useMarketingGroupDetail(groupId);
  // Only poll via useSearchStatus — useMarketingClients is invalidated by status changes
  const { data: clientsData } = useMarketingClients(groupId, {
    limit: pageSize,
    offset: (page - 1) * pageSize,
    q: searchQuery || undefined,
    search_status: searchStatusFilter || undefined,
  });
  const canManage = hasPermission("marketing.manage");

  const group = data?.group;
  const stats = data?.stats;
  const clients = clientsData?.clients ?? [];
  const totalClients = clientsData?.total ?? 0;
  const totalPages = Math.ceil(totalClients / pageSize);
  const igScrapeIncompleteCount = getGroupIgScrapeIncompleteCount(clients);

  // Poll search status while searching
  const searchStatusEnabled = group?.status === "searching";
  const { data: searchStatus } = useSearchStatus(groupId, searchStatusEnabled);

  const startSearchMutation = useStartGroupSearch();
  const bulkApproveMutation = useBulkApproveGroupContacts();
  const exportMutation = useExportGroupClients();

  const statusCfg = statusConfig[group?.status ?? "draft"];
  const showDoneWarning =
    group?.status === "done" && igScrapeIncompleteCount > 0;

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

  const isSearching =
    searchStatus?.status === "searching" || group?.status === "searching";

  if (isLoading) {
    return (
      <div className="space-y-6">
        {/* Skeleton header */}
        <div className="flex items-center gap-4">
          <div className="h-10 w-10 animate-pulse rounded-lg bg-gray-200 dark:bg-gray-700" />
          <div className="space-y-2">
            <div className="h-6 w-48 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
            <div className="h-4 w-32 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
          </div>
        </div>
        {/* Skeleton stats cards */}
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-7">
          {Array.from({ length: 7 }).map((_, i) => (
            <div
              key={i}
              className="h-20 animate-pulse rounded-lg bg-gray-200 dark:bg-gray-700"
            />
          ))}
        </div>
        {/* Skeleton client rows */}
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="h-16 animate-pulse rounded-lg bg-gray-200 dark:bg-gray-700"
            />
          ))}
        </div>
      </div>
    );
  }

  if (error || !group) {
    return (
      <div className="space-y-4">
        <Link
          to="/marketing"
          className="inline-flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
        >
          <ArrowLeft className="h-4 w-4" /> Kembali
        </Link>
        <Card className="border-red-200 dark:border-red-800 py-8 text-center">
          <p className="text-red-600 dark:text-red-400">
            Gagal memuat data group:{" "}
            {(error as Error)?.message ?? "Unknown error"}
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link
            to="/marketing"
            className="rounded-lg p-2 text-gray-500 transition-colors hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                {group.name}
              </h1>
              <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                {CLIENT_TYPE_LABELS[group.client_type] ?? group.client_type}
              </span>
            </div>
            <div className="mt-1 flex items-center gap-2">
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold",
                  showDoneWarning
                    ? "bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300"
                    : statusCfg.bg,
                  showDoneWarning
                    ? "border border-amber-200 dark:border-amber-800"
                    : statusCfg.color,
                )}
              >
                {showDoneWarning ? (
                  <XCircle className="h-3 w-3" />
                ) : (
                  <statusCfg.icon
                    className={cn("h-3 w-3", isSearching && "animate-spin")}
                  />
                )}
                {showDoneWarning ? "Done with IG warnings" : statusCfg.label}
              </span>
              <span className="text-xs text-gray-400">
                {formatDate(group.created_at)}
              </span>
            </div>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex flex-wrap items-center gap-2">
          {canManage && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={handleBulkApprove}
                loading={bulkApproveMutation.isPending}
                disabled={clients.flatMap((c) => c.contacts ?? []).length === 0}
              >
                <CheckCircle2 className="h-4 w-4" />
                Approve Semua
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleExport}
                loading={exportMutation.isPending}
                disabled={clients.length === 0}
              >
                <Download className="h-4 w-4" />
                Export Excel
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setImportOpen(true)}
              >
                <Upload className="h-4 w-4" />
                Upload Excel
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setAddClientOpen(true)}
              >
                <Plus className="h-4 w-4" />
                Tambah Client
              </Button>
              {group.status !== "searching" && (
                <Button
                  size="sm"
                  onClick={handleStartSearch}
                  loading={startSearchMutation.isPending}
                >
                  <Play className="h-4 w-4" />
                  Mulai Scraping
                </Button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Stats cards */}
      {stats && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-7">
          {[
            {
              label: "Total",
              value: stats.total,
              color: "text-gray-900 dark:text-gray-100",
            },
            {
              label: "Ditemukan",
              value: stats.found,
              color: "text-green-600 dark:text-green-400",
            },
            {
              label: "Partial",
              value: stats.partial,
              color: "text-amber-600 dark:text-amber-400",
            },
            {
              label: "Tidak Ditemukan",
              value: stats.not_found,
              color: "text-red-500",
            },
            {
              label: "Error",
              value: stats.error_count,
              color: "text-amber-600 dark:text-amber-400",
            },
            {
              label: "Pending",
              value: stats.pending,
              color: "text-blue-600 dark:text-blue-400",
            },
            {
              label: "Approved",
              value: stats.approved,
              color: "text-indigo-600 dark:text-indigo-400",
            },
          ].map((s) => (
            <Card key={s.label} padding={false}>
              <div className="p-4">
                <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
                  {s.label}
                </p>
                <p className={cn("mt-1 text-2xl font-bold", s.color)}>
                  {s.value}
                </p>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Search progress */}
      {isSearching && searchStatus && (
        <Card>
          <CardHeader>
            <CardTitle>Progress Scraping</CardTitle>
          </CardHeader>
          <SearchProgressBar
            status={searchStatus.status}
            progress={searchStatus.progress}
            total={searchStatus.total}
            found={searchStatus.found}
            not_found={searchStatus.not_found}
          />
          {searchStatus.error_message && (
            <p className="mt-2 text-xs text-red-500">
              {searchStatus.error_message}
            </p>
          )}
        </Card>
      )}

      {/* Group-level search error (entire background job crashed) */}
      {searchStatus?.group_search_error && (
        <Card className="border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950/20">
          <div className="flex items-start gap-3">
            <XCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-600 dark:text-red-300" />
            <div className="space-y-1">
              <p className="text-sm font-semibold text-red-900 dark:text-red-100">
                Scraping gagal
              </p>
              <p className="text-xs text-red-800 dark:text-red-200">
                {searchStatus.group_search_error}
              </p>
            </div>
          </div>
        </Card>
      )}

      {showDoneWarning && (
        <Card className="border-amber-200 bg-amber-50/70 dark:border-amber-900/60 dark:bg-amber-950/20">
          <div className="flex items-start gap-3">
            <XCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600 dark:text-amber-300" />
            <div className="space-y-1">
              <p className="text-sm font-semibold text-amber-900 dark:text-amber-100">
                Search selesai, tapi sebagian IG post belum berhasil discrape
              </p>
              <p className="text-xs text-amber-800 dark:text-amber-200">
                {igScrapeIncompleteCount} client sudah punya handle IG, tetapi
                belum punya post tersimpan. Ini biasanya berarti handle
                ditemukan, namun provider post scrape tidak mengembalikan data.
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Ready to blast panel */}
      <MarketingReadyToBlastPanel clients={clients} groupId={groupId} />

      {/* Add client inline form */}
      {addClientOpen && (
        <Card>
          <h3 className="mb-3 text-sm font-semibold text-gray-700 dark:text-gray-300">
            Tambah Client Baru
          </h3>
          <AddClientInlineForm
            groupId={groupId}
            onClose={() => setAddClientOpen(false)}
          />
        </Card>
      )}

      {/* AI Group Memory */}
      <GroupStrategyPanel groupId={groupId} />

      {/* Clients list */}
      <div>
        {/* Header + search + filter */}
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
            Daftar Client ({totalClients} total
            {searchQuery ? ` — hasil filter` : ""})
          </h2>
          <div className="flex flex-wrap items-center gap-2">
            {/* Search input */}
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setPage(1);
                }}
                placeholder="Cari client..."
                className="h-8 w-48 rounded-lg border border-gray-300 pl-8 pr-3 text-sm
                  focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500
                  dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
              />
            </div>
            {/* Status filter */}
            <select
              value={searchStatusFilter}
              onChange={(e) => {
                setSearchStatusFilter(e.target.value);
                setPage(1);
              }}
              className="h-8 rounded-lg border border-gray-300 px-2 text-sm
                focus:border-indigo-500 focus:outline-none
                dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
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
          <Card className="flex flex-col items-center justify-center py-12 text-center">
            <Users className="mb-3 h-10 w-10 text-gray-300 dark:text-gray-600" />
            <p className="mb-4 text-sm text-gray-500 dark:text-gray-400">
              {searchQuery || searchStatusFilter
                ? "Tidak ada client yang cocok dengan filter"
                : "Belum ada client di group ini"}
            </p>
            {canManage && !searchQuery && !searchStatusFilter && (
              <Button onClick={() => setAddClientOpen(true)}>
                <Plus className="h-4 w-4" />
                Tambah Client Pertama
              </Button>
            )}
          </Card>
        )}

        {/* Client table */}
        {clients.length > 0 && (
          <>
            <MarketingClientResultsTable
              clients={clients}
              groupId={groupId}
              canManage={canManage}
            />
            {/* Pagination */}
            {totalPages > 1 && (
              <div className="mt-4 flex items-center justify-between">
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Menampilkan {(page - 1) * pageSize + 1}–
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
