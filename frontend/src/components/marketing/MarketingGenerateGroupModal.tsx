import { useState } from "react";
import { Modal } from "../ui/Modal";
import { Button } from "../ui/Button";
import { Select } from "../ui/Select";
import {
  useGenerateMarketingPreview,
  useConfirmGeneratedGroup,
} from "../../hooks/useMarketing";
import { type ClientType, CLIENT_TYPE_LABELS } from "../../api/marketing";
import toast from "react-hot-toast";
import { useNavigate } from "react-router-dom";
import {
  Sparkles,
  X,
  Plus,
  ChevronLeft,
  ChevronDown,
  ChevronUp,
  Loader2,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";

// ── Client type options (all 11 types) ────────────────────────────────────

const CLIENT_TYPE_OPTIONS: { value: ClientType; label: string }[] = [
  { value: "lembaga_negara", label: "Lembaga Negara Non Kementerian" },
  { value: "kementerian", label: "Kementerian" },
  { value: "bumn", label: "BUMN" },
  { value: "swasta_besar", label: "Perusahaan Swasta Besar" },
  { value: "asosiasi", label: "Asosiasi" },
  { value: "lpk", label: "Lembaga Pelatihan Kerja (LPK)" },
  { value: "lkp", label: "Lembaga Karier (LKP)" },
  { value: "lsp_p1", label: "LSP P1" },
  { value: "lsp_p2", label: "LSP P2" },
  { value: "lsp_p3", label: "LSP P3" },
  { value: "dinas", label: "Dinas" },
];

// ── Internal step machine ───────────────────────────────────────────────────

type Step = "setup" | "review" | "done" | "error";

interface ModalState {
  step: Step;
  clientType: ClientType;
  count: number;
  names: string[];
  groundingUrls: string[];
  excludedCount: number;
  groupId?: number;
  groupName?: string;
  error?: string;
}

// ── Component ─────────────────────────────────────────────────────────────────

interface MarketingGenerateGroupModalProps {
  onClose: () => void;
}

const INITIAL_STATE: ModalState = {
  step: "setup",
  clientType: "kementerian",
  count: 50,
  names: [],
  groundingUrls: [],
  excludedCount: 0,
};

export function MarketingGenerateGroupModal({
  onClose,
}: MarketingGenerateGroupModalProps) {
  const [state, setState] = useState<ModalState>(INITIAL_STATE);
  const [manualName, setManualName] = useState("");
  const [groundingOpen, setGroundingOpen] = useState(false);
  const navigate = useNavigate();

  const previewMutation = useGenerateMarketingPreview();
  const confirmMutation = useConfirmGeneratedGroup();

  // ── Step 1: Generate ──────────────────────────────────────────────────────

  async function handleGenerate() {
    try {
      const result = await previewMutation.mutateAsync({
        client_type: state.clientType,
        count: state.count,
      });
      setState((s) => ({
        ...s,
        step: "review",
        names: result.names,
        groundingUrls: result.grounding_urls,
        excludedCount: result.excluded_count ?? 0,
        error: undefined,
      }));
    } catch {
      setState((s) => ({
        ...s,
        step: "error",
        error: "Gagal generate nama. Silakan coba lagi.",
      }));
    }
  }

  // ── Step 2: Review actions ────────────────────────────────────────────────

  function handleDeleteName(index: number) {
    setState((s) => ({
      ...s,
      names: s.names.filter((_, i) => i !== index),
    }));
  }

  function handleAddManualName() {
    const trimmed = manualName.trim();
    if (!trimmed) return;
    setState((s) => ({ ...s, names: [...s.names, trimmed] }));
    setManualName("");
  }

  async function handleCreateGroup() {
    try {
      const result = await confirmMutation.mutateAsync({
        client_type: state.clientType,
        names: state.names,
      });
      setState((s) => ({
        ...s,
        step: "done",
        groupId: result.group_id,
        groupName: result.group_name,
        error: undefined,
      }));
    } catch {
      setState((s) => ({
        ...s,
        step: "error",
        error: "Gagal membuat group. Silakan coba lagi.",
      }));
    }
  }

  // ── Reset ──────────────────────────────────────────────────────────────────

  function handleReset() {
    setState(INITIAL_STATE);
    setManualName("");
    setGroundingOpen(false);
  }

  // ── Derived state ─────────────────────────────────────────────────────────

  const loadingGenerate = previewMutation.isPending;
  const loadingCreate = confirmMutation.isPending;
  const isLoading = loadingGenerate || loadingCreate;

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <Modal
      isOpen
      onClose={onClose}
      title={
        state.step === "done"
          ? "Group Berhasil Dibuat"
          : state.step === "error"
            ? "Terjadi Kesalahan"
            : "Buat Group dengan AI"
      }
      size="lg"
    >
      {/* Step indicator (hidden on done/error) */}
      {state.step !== "done" && state.step !== "error" && (
        <div className="mb-6 flex items-center gap-0">
          {(["setup", "review"] as const).map((s, i) => {
            const active = state.step === s;
            const completed =
              (s === "setup" && state.step === "review") ||
              state.step === "done";
            return (
              <div key={s} className="flex items-center">
                <div
                  className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold transition-colors ${
                    completed
                      ? "bg-indigo-600 text-white"
                      : active
                        ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-900 dark:text-indigo-300 ring-2 ring-indigo-500"
                        : "bg-gray-100 text-gray-400 dark:bg-gray-700 dark:text-gray-500"
                  }`}
                >
                  {completed ? <CheckCircle2 className="h-4 w-4" /> : i + 1}
                </div>
                <span
                  className={`ml-2 text-sm font-medium ${
                    active || completed
                      ? "text-gray-900 dark:text-gray-100"
                      : "text-gray-400 dark:text-gray-500"
                  }`}
                >
                  {s === "setup" ? "Pilih Kategori" : "Review Nama"}
                </span>
                {i < 1 && (
                  <div
                    className={`mx-3 h-px flex-1 ${
                      completed
                        ? "bg-indigo-400"
                        : "bg-gray-200 dark:bg-gray-700"
                    }`}
                    style={{ minWidth: 24 }}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ── Step 1: Setup ──────────────────────────────────────────────────── */}
      {state.step === "setup" && (
        <div className="space-y-5">
          <div className="rounded-lg border border-indigo-100 bg-indigo-50 p-4 dark:border-indigo-900 dark:bg-indigo-950/30">
            <div className="flex items-start gap-3">
              <Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-indigo-600 dark:text-indigo-400" />
              <div>
                <p className="text-sm font-medium text-indigo-900 dark:text-indigo-100">
                  Generate Nama Client dengan AI
                </p>
                <p className="mt-1 text-xs text-indigo-700 dark:text-indigo-300">
                  Gemini akan Mencari nama client berdasarkan kategori yang
                  dipilih. Hasilnya bisa diedit sebelum membuat group.
                </p>
              </div>
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Tipe Client
            </label>
            <Select
              value={state.clientType}
              onChange={(v) =>
                setState((s) => ({ ...s, clientType: v as ClientType }))
              }
              options={CLIENT_TYPE_OPTIONS}
              className="w-full"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Jumlah Nama yang Dihasilkan
            </label>
            <input
              type="number"
              min={5}
              max={200}
              value={state.count}
              onChange={(e) =>
                setState((s) => ({
                  ...s,
                  count: Math.max(
                    5,
                    Math.min(200, Number(e.target.value) || 50),
                  ),
                }))
              }
              className="w-40 rounded-lg border border-gray-300 px-3 py-2 text-sm
                focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500
                dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
            />
            <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">
              Minimal 5, maksimal 200
            </p>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={onClose} disabled={isLoading}>
              Batal
            </Button>
            <Button
              onClick={handleGenerate}
              loading={loadingGenerate}
              disabled={isLoading}
            >
              <Sparkles className="h-4 w-4" />
              Generate dengan AI
            </Button>
          </div>
        </div>
      )}

      {/* ── Step 2: Review ─────────────────────────────────────────────────── */}
      {state.step === "review" && (
        <div className="space-y-4">
          {/* Header with count badge */}
          <div className="flex items-center justify-between">
            <span className="rounded-full bg-indigo-100 px-3 py-1 text-sm font-semibold text-indigo-700 dark:bg-indigo-900 dark:text-indigo-300">
              {state.names.length} nama dihasilkan
            </span>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {CLIENT_TYPE_LABELS[state.clientType]}
            </span>
          </div>

          {/* Exclusion notice */}
          {state.excludedCount > 0 && (
            <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                <strong>{state.excludedCount} nama</strong> sudah ada di
                database untuk kategori ini dan otomatis dikeluarkan dari list.
              </span>
            </div>
          )}

          {/* Name list */}
          <div className="max-h-64 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700">
            {state.names.length === 0 ? (
              <div className="p-6 text-center text-sm text-gray-400 dark:text-gray-500">
                Tidak ada nama. Tambahkan secara manual.
              </div>
            ) : (
              <ul className="divide-y divide-gray-100 dark:divide-gray-700">
                {state.names.map((name, i) => (
                  <li
                    key={i}
                    className="flex items-center justify-between px-4 py-2"
                  >
                    <span className="text-sm text-gray-800 dark:text-gray-200">
                      {name}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleDeleteName(i)}
                      className="ml-2 shrink-0 rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/20"
                      title="Hapus"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Add manual name */}
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={manualName}
              onChange={(e) => setManualName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleAddManualName();
              }}
              placeholder="Tambah nama manual..."
              className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm
                focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500
                dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
            />
            <Button
              variant="secondary"
              onClick={handleAddManualName}
              disabled={!manualName.trim()}
            >
              <Plus className="h-4 w-4" />
              Tambah
            </Button>
          </div>

          {/* Grounding sources (collapsible) */}
          {state.groundingUrls.length > 0 && (
            <div className="rounded-lg border border-gray-200 dark:border-gray-700">
              <button
                type="button"
                onClick={() => setGroundingOpen((v) => !v)}
                className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800"
              >
                <span>Sumber AI ({state.groundingUrls.length} sumber)</span>
                {groundingOpen ? (
                  <ChevronUp className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
              </button>
              {groundingOpen && (
                <ul className="border-t border-gray-200 px-4 py-2 dark:border-gray-700">
                  {state.groundingUrls.map((url, i) => (
                    <li key={i}>
                      <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block py-1 text-xs text-indigo-600 hover:underline dark:text-indigo-400"
                      >
                        {url}
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Navigation */}
          <div className="flex justify-between gap-2 pt-2">
            <Button
              variant="secondary"
              onClick={() =>
                setState((s) => ({ ...s, step: "setup", error: undefined }))
              }
              disabled={isLoading}
            >
              <ChevronLeft className="h-4 w-4" />
              Kembali
            </Button>
            <Button
              onClick={handleCreateGroup}
              loading={loadingCreate}
              disabled={isLoading || state.names.length === 0}
            >
              {loadingCreate ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  <CheckCircle2 className="h-4 w-4" />
                  Buat Group & Mulai Scraping
                </>
              )}
            </Button>
          </div>
        </div>
      )}

      {/* ── Step 3: Done ────────────────────────────────────────────────────── */}
      {state.step === "done" && (
        <div className="space-y-5 py-4 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
            <CheckCircle2 className="h-8 w-8 text-green-600 dark:text-green-400" />
          </div>
          <div>
            <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Group "{state.groupName}" berhasil dibuat
            </p>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {state.names.length} clients ditambahkan
            </p>
          </div>
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-800">
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Scraping pipeline sudah dimulai di background. Anda bisa monitor
              progress di halaman group.
            </p>
          </div>
          <div className="flex justify-center gap-3">
            <Button variant="secondary" onClick={handleReset}>
              <Plus className="h-4 w-4" />
              Buat Lagi
            </Button>
            {state.groupId && (
              <Button
                onClick={() => {
                  onClose();
                  navigate(`/marketing/groups/${state.groupId}`);
                }}
              >
                Lihat Group
              </Button>
            )}
          </div>
        </div>
      )}

      {/* ── Error state ─────────────────────────────────────────────────────── */}
      {state.step === "error" && (
        <div className="space-y-4 py-4">
          <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-950/30">
            <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-600 dark:text-red-400" />
            <div>
              <p className="text-sm font-medium text-red-900 dark:text-red-100">
                Gagal generate nama
              </p>
              <p className="mt-1 text-xs text-red-700 dark:text-red-300">
                {state.error ?? "Terjadi kesalahan yang tidak diketahui."}
              </p>
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={onClose}>
              Tutup
            </Button>
            <Button
              onClick={() =>
                setState((s) => ({ ...s, step: "setup", error: undefined }))
              }
            >
              Coba Lagi
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
