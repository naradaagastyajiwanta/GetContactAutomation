import { useState, useEffect, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import {
  UserSearch,
  Plus,
  Play,
  Clock,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Search,
  Building2,
  User,
} from "lucide-react";
import {
  useCrmRequests,
  useCrmStats,
  useCreateCrmRequest,
  useRunCrmProfiling,
} from "../hooks/useCrm";
import { searchDmsPics, type DmsPicResult } from "../api/dms";
import { Card } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Spinner } from "../components/ui/Spinner";
import { EmptyState } from "../components/ui/EmptyState";
import { Modal } from "../components/ui/Modal";
import { formatDate } from "../lib/utils";
import { useAuth } from "../context/AuthContext";
import { usePageTour } from "../hooks/usePageTour";
import { CRM_TOUR_STEPS } from "../tours/crm.tour";

const statusConfig: Record<
  string,
  { label: string; variant: string; icon: typeof Clock }
> = {
  pending: {
    label: "Pending",
    variant:
      "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
    icon: Clock,
  },
  processing: {
    label: "Processing",
    variant: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
    icon: Loader2,
  },
  completed: {
    label: "Completed",
    variant:
      "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
    icon: CheckCircle2,
  },
  failed: {
    label: "Failed",
    variant: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
    icon: AlertCircle,
  },
};

function StatusBadge({ status }: { status: string }) {
  const cfg = statusConfig[status] || statusConfig.pending;
  const Icon = cfg.icon;
  return (
    <Badge variant={cfg.variant}>
      <Icon
        className={`mr-1 h-3 w-3 ${status === "processing" ? "animate-spin" : ""}`}
      />
      {cfg.label}
    </Badge>
  );
}

function NewRequestModal({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) {
  const [mode, setMode] = useState<"dms" | "manual">("dms");
  const [search, setSearch] = useState("");
  const [picResults, setPicResults] = useState<DmsPicResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<DmsPicResult | null>(null);

  // Manual input fields
  const [picName, setPicName] = useState("");
  const [uniName, setUniName] = useState("");
  const [picTitle, setPicTitle] = useState("");
  const [notes, setNotes] = useState("");

  const createMutation = useCreateCrmRequest();
  const runMutation = useRunCrmProfiling();
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  // Debounced search — fires on keyword change
  const doSearch = useCallback(async (q: string) => {
    setSearching(true);
    try {
      const res = await searchDmsPics(q, 30);
      setPicResults(res.pics);
    } catch {
      setPicResults([]);
    } finally {
      setSearching(false);
    }
  }, []);

  useEffect(() => {
    if (mode !== "dms") return;
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(search), 300);
    return () => clearTimeout(debounceRef.current);
  }, [search, mode, doSearch]);

  // Load initial results when modal opens in DMS mode
  useEffect(() => {
    if (isOpen && mode === "dms" && picResults.length === 0 && !searching) {
      doSearch("");
    }
  }, [isOpen, mode]); // eslint-disable-line react-hooks/exhaustive-deps

  function resetState() {
    setSearch("");
    setPicResults([]);
    setSelected(null);
    setPicName("");
    setUniName("");
    setPicTitle("");
    setNotes("");
  }

  async function handleSubmit() {
    const name = mode === "dms" ? selected?.nama_pic : picName.trim();
    if (!name) return;

    const university =
      mode === "dms"
        ? selected?.nama_universitas || undefined
        : uniName.trim() || undefined;
    const title =
      mode === "dms"
        ? selected?.jabatan_pic || undefined
        : picTitle.trim() || undefined;

    const result = await createMutation.mutateAsync({
      pic_name: name,
      university_name: university,
      pic_title: title,
      notes: notes.trim() || undefined,
    });
    await runMutation.mutateAsync(result.id);
    resetState();
    onClose();
  }

  const loading = createMutation.isPending || runMutation.isPending;

  return (
    <Modal
      isOpen={isOpen}
      onClose={() => {
        resetState();
        onClose();
      }}
      title="New PIC Profile Request"
    >
      <div className="space-y-4">
        {/* Mode toggle */}
        <div className="flex rounded-lg bg-gray-100 p-1 dark:bg-gray-800">
          <button
            type="button"
            onClick={() => {
              setMode("dms");
              setSelected(null);
            }}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              mode === "dms"
                ? "bg-white text-gray-900 shadow dark:bg-gray-700 dark:text-gray-100"
                : "text-gray-500 hover:text-gray-700 dark:text-gray-400"
            }`}
          >
            <Building2 className="mr-1.5 inline h-4 w-4" />
            Dari DMS
          </button>
          <button
            type="button"
            onClick={() => setMode("manual")}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              mode === "manual"
                ? "bg-white text-gray-900 shadow dark:bg-gray-700 dark:text-gray-100"
                : "text-gray-500 hover:text-gray-700 dark:text-gray-400"
            }`}
          >
            <User className="mr-1.5 inline h-4 w-4" />
            Manual
          </button>
        </div>

        {mode === "dms" ? (
          <>
            {/* Search bar */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setSelected(null);
                }}
                placeholder="Cari nama PIC atau universitas..."
                className="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                autoFocus
              />
            </div>

            {/* Selected PIC preview */}
            {selected && (
              <div className="flex items-center gap-3 rounded-lg border-2 border-indigo-500 bg-indigo-50 p-3 dark:border-indigo-400 dark:bg-indigo-950">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-indigo-100 dark:bg-indigo-900">
                  <User className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-gray-900 dark:text-gray-100">
                    {selected.nama_pic}
                  </p>
                  <p className="truncate text-sm text-gray-500 dark:text-gray-400">
                    {selected.jabatan_pic && `${selected.jabatan_pic} — `}
                    {selected.nama_universitas || "—"}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setSelected(null)}
                  className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                >
                  Ganti
                </button>
              </div>
            )}

            {/* PIC list */}
            {!selected && (
              <div className="max-h-64 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700">
                {searching ? (
                  <div className="flex items-center justify-center py-8">
                    <Spinner size="sm" />
                    <span className="ml-2 text-sm text-gray-500">
                      Mencari...
                    </span>
                  </div>
                ) : picResults.length === 0 ? (
                  <div className="py-8 text-center text-sm text-gray-500 dark:text-gray-400">
                    {search
                      ? "Tidak ditemukan PIC yang cocok"
                      : "Belum ada data PIC di DMS"}
                  </div>
                ) : (
                  picResults.map((pic, i) => (
                    <button
                      key={`${pic.nama_pic}-${pic.id_univ}-${i}`}
                      type="button"
                      onClick={() => setSelected(pic)}
                      className="flex w-full items-center gap-3 border-b border-gray-100 px-3 py-2.5 text-left transition-colors last:border-b-0 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800"
                    >
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gray-100 dark:bg-gray-800">
                        <User className="h-4 w-4 text-gray-500 dark:text-gray-400" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                          {pic.nama_pic}
                        </p>
                        <p className="truncate text-xs text-gray-500 dark:text-gray-400">
                          {pic.jabatan_pic && `${pic.jabatan_pic} — `}
                          {pic.nama_universitas || "—"}
                        </p>
                      </div>
                      <span className="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-400 dark:bg-gray-800">
                        {pic.pic_source === "universitas"
                          ? "Univ"
                          : pic.pic_source === "kontak_universitas"
                            ? "Kontak"
                            : "Jadwal"}
                      </span>
                    </button>
                  ))
                )}
              </div>
            )}
          </>
        ) : (
          /* Manual input mode */
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                Nama PIC *
              </label>
              <input
                type="text"
                value={picName}
                onChange={(e) => setPicName(e.target.value)}
                placeholder="Dr. Bambang Sutrisno"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                Universitas
              </label>
              <input
                type="text"
                value={uniName}
                onChange={(e) => setUniName(e.target.value)}
                placeholder="Universitas Brawijaya"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                Jabatan
              </label>
              <input
                type="text"
                value={picTitle}
                onChange={(e) => setPicTitle(e.target.value)}
                placeholder="Rektor, Wakil Rektor, Dekan, ..."
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
              />
            </div>
          </div>
        )}

        {/* Notes — always shown */}
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
            Catatan
          </label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            placeholder="Catatan tambahan..."
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
          />
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-2 pt-2">
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              resetState();
              onClose();
            }}
          >
            Batal
          </Button>
          <Button
            onClick={handleSubmit}
            loading={loading}
            disabled={mode === "dms" ? !selected : !picName.trim()}
          >
            <Play className="h-4 w-4" />
            Buat & Jalankan
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export default function CrmPage() {
  const { hasPermission } = useAuth();
  const [modalOpen, setModalOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const { data, isLoading } = useCrmRequests({
    status: statusFilter || undefined,
    limit: 50,
  });
  const { data: stats } = useCrmStats();
  const runMutation = useRunCrmProfiling();
  const canManageCrm = hasPermission("crm.manage");
  usePageTour("crm", CRM_TOUR_STEPS);

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            PIC Profiling
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            OSINT intelligence gathering untuk PIC universitas
          </p>
        </div>
        {canManageCrm && (
          <div data-tour="crm-new-btn">
            <Button onClick={() => setModalOpen(true)}>
              <Plus className="h-4 w-4" />
              New Request
            </Button>
          </div>
        )}
      </div>

      {/* Stats cards */}
      {stats && (
        <div
          data-tour="crm-stats"
          className="grid grid-cols-2 gap-4 sm:grid-cols-4"
        >
          {[
            {
              label: "Total",
              value: stats.total_requests,
              color: "text-gray-900 dark:text-gray-100",
            },
            {
              label: "Completed",
              value: stats.completed,
              color: "text-green-600 dark:text-green-400",
            },
            {
              label: "Processing",
              value: stats.processing,
              color: "text-blue-600 dark:text-blue-400",
            },
            {
              label: "Avg Confidence",
              value: `${Math.round(stats.avg_completion_confidence * 100)}%`,
              color: "text-indigo-600 dark:text-indigo-400",
            },
          ].map((s) => (
            <Card key={s.label}>
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
                {s.label}
              </p>
              <p className={`mt-1 text-2xl font-bold ${s.color}`}>{s.value}</p>
            </Card>
          ))}
        </div>
      )}

      {/* Filter tabs */}
      <div data-tour="crm-status-filter" className="flex gap-2">
        {["", "pending", "processing", "completed", "failed"].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              statusFilter === s
                ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
                : "text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
            }`}
          >
            {s === "" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>

      {/* Request list */}
      {!data?.requests?.length ? (
        <EmptyState
          icon={UserSearch}
          title="No profiling requests"
          description="Create a new request to start gathering PIC intelligence"
          action={
            canManageCrm ? (
              <Button onClick={() => setModalOpen(true)}>
                <Plus className="h-4 w-4" /> New Request
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="space-y-3">
          {data.requests.map((req) => (
            <Link key={req.id} to={`/crm/${req.id}`}>
              <Card className="flex items-center justify-between transition-colors hover:border-indigo-300 dark:hover:border-indigo-600">
                <div className="flex items-center gap-4">
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-100 dark:bg-indigo-900">
                    <UserSearch className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
                  </div>
                  <div>
                    <p className="font-semibold text-gray-900 dark:text-gray-100">
                      {req.pic_name}
                    </p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      {req.university_name || "—"}{" "}
                      {req.pic_title && `• ${req.pic_title}`}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-xs text-gray-400 dark:text-gray-500">
                    {formatDate(req.created_at)}
                  </span>
                  <StatusBadge status={req.status} />
                  {canManageCrm && req.status === "pending" && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        runMutation.mutate(req.id);
                      }}
                      loading={runMutation.isPending}
                    >
                      <Play className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}

      {canManageCrm && (
        <NewRequestModal
          isOpen={modalOpen}
          onClose={() => setModalOpen(false)}
        />
      )}
    </div>
  );
}
