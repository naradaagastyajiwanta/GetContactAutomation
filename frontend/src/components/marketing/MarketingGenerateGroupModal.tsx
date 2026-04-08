import { useState, useRef, useEffect } from "react";
import { driver } from "driver.js";
import * as XLSX from "xlsx";
import { Modal } from "../ui/Modal";
import { Button } from "../ui/Button";
import { Select } from "../ui/Select";
import {
  useGenerateMarketingPreview,
  useConfirmGeneratedGroup,
} from "../../hooks/useMarketing";
import { type ClientType, CLIENT_TYPE_LABELS } from "../../api/marketing";
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
  ClipboardList,
  Upload,
  FileSpreadsheet,
} from "lucide-react";
import { cn } from "../../lib/utils";

// ── Client type options ─────────────────────────────────────────────────────

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

// ── Types ───────────────────────────────────────────────────────────────────

type InputTab = "gemini" | "paste" | "upload";
type Step = "setup" | "review" | "done";

interface ModalState {
  step: Step;
  clientType: ClientType;
  count: number;
  names: string[];
  groundingUrls: string[];
  excludedCount: number;
  inputSource: InputTab;
  inputSourceLabel: string;
  groupId?: number;
  groupName?: string;
}

const INITIAL_STATE: ModalState = {
  step: "setup",
  clientType: "kementerian",
  count: 50,
  names: [],
  groundingUrls: [],
  excludedCount: 0,
  inputSource: "gemini",
  inputSourceLabel: "AI",
};

// ── File parsing helpers ────────────────────────────────────────────────────

const NAME_KEYWORDS = [
  "nama",
  "name",
  "company",
  "institution",
  "lembaga",
  "instansi",
  "perusahaan",
  "client",
  "organisasi",
];

function findNameColumnIndex(header: unknown[]): number {
  for (let i = 0; i < header.length; i++) {
    const h = String(header[i] ?? "")
      .toLowerCase()
      .trim();
    if (NAME_KEYWORDS.some((kw) => h.includes(kw))) return i;
  }
  return 0; // fallback: first column
}

function parseFileForNames(file: File): Promise<string[]> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const wb = XLSX.read(e.target?.result, { type: "binary" });
        const ws = wb.Sheets[wb.SheetNames[0]];
        const rows = XLSX.utils.sheet_to_json<unknown[]>(ws, {
          header: 1,
        }) as unknown[][];

        if (rows.length === 0) {
          resolve([]);
          return;
        }

        const header = rows[0] as unknown[];
        const colIdx = findNameColumnIndex(header);
        // If header row has a name keyword, skip it; otherwise include row 0
        const hasHeader = NAME_KEYWORDS.some((kw) =>
          String(header[colIdx] ?? "")
            .toLowerCase()
            .includes(kw),
        );
        const dataRows = hasHeader ? rows.slice(1) : rows;

        const names = dataRows
          .map((row) => String((row as unknown[])[colIdx] ?? "").trim())
          .filter(Boolean);

        resolve(names);
      } catch (err) {
        reject(err);
      }
    };
    reader.onerror = () => reject(new Error("Gagal membaca file"));
    reader.readAsBinaryString(file);
  });
}

function parsePasteText(text: string): string[] {
  // Split by newline or comma, trim, deduplicate, filter empty
  const raw = text
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const seen = new Set<string>();
  return raw.filter((n) => {
    const key = n.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function getErrorMessage(errorType?: string, detail?: string): string {
  if (errorType === "timeout") {
    return "Gemini membutuhkan terlalu lama merespons. Coba lagi atau kurangi jumlah nama.";
  }
  if (errorType === "all_duplicates") {
    return "Semua nama yang dihasilkan sudah ada di database. Coba tipe client lain atau hapus group lama.";
  }
  if (errorType === "parse_error") {
    return "Gemini mengembalikan format yang tidak valid. Coba lagi.";
  }
  return detail || "Terjadi kesalahan. Coba lagi.";
}

// ── Component ───────────────────────────────────────────────────────────────

interface MarketingGenerateGroupModalProps {
  onClose: () => void;
  onGroupCreated?: (groupId: number) => void;
  isOnboarding?: boolean;
}

export function MarketingGenerateGroupModal({
  onClose,
  onGroupCreated,
  isOnboarding,
}: MarketingGenerateGroupModalProps) {
  const [state, setState] = useState<ModalState>(INITIAL_STATE);
  const [activeTab, setActiveTab] = useState<InputTab>("gemini");

  useEffect(() => {
    if (!isOnboarding) return;
    const timer = setTimeout(() => {
      const d = driver({
        animate: true,
        overlayOpacity: 0.55,
        stagePadding: 8,
        popoverOffset: 14,
        showProgress: true,
        progressText: "{{current}} / {{total}}",
        nextBtnText: "Lanjut →",
        prevBtnText: "← Kembali",
        doneBtnText: "Paham, Mulai! →",
        allowClose: true,
        steps: [
          {
            element: '[data-tour="modal-client-type"]',
            popover: {
              title: "🏷️ Tipe Client",
              description:
                "Pilih kategori industri target grupmu: BUMN, Kementerian, Swasta Besar, Asosiasi, dll. Ini mempengaruhi cara AI mencari nama klien yang relevan.",
              side: "bottom",
            },
          },
          {
            element: '[data-tour="modal-input-tabs"]',
            popover: {
              title: "3 Cara Input Nama Client",
              description:
                "<b>Generate AI</b> — Gemini buat daftar otomatis dari Google Search.<br><b>Paste Nama</b> — tempel daftar nama langsung.<br><b>Upload File</b> — upload Excel atau CSV berisi nama klien.",
              side: "bottom",
            },
          },
          {
            element: '[data-tour="modal-gemini-area"]',
            popover: {
              title: "⚡ Generate dengan AI",
              description:
                "Set jumlah nama yang ingin di-generate, lalu klik <b>Generate dengan AI</b>. Gemini akan mencari nama institusi nyata sesuai tipe yang dipilih. Request besar dibagi otomatis per batch.",
              side: "top",
            },
          },
        ],
      });
      d.drive();
    }, 400);
    return () => clearTimeout(timer);
  }, [isOnboarding]);

  // Gemini tab state
  const [geminiError, setGeminiError] = useState<string | null>(null);

  // Paste tab state
  const [pasteText, setPasteText] = useState("");

  // Upload tab state
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadNames, setUploadNames] = useState<string[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadParsing, setUploadParsing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Review step state
  const [manualName, setManualName] = useState("");
  const [groundingOpen, setGroundingOpen] = useState(false);

  const navigate = useNavigate();
  const previewMutation = useGenerateMarketingPreview();
  const confirmMutation = useConfirmGeneratedGroup();

  const loadingCreate = confirmMutation.isPending;

  // ── Tab switching ──────────────────────────────────────────────────────────

  function handleTabChange(tab: InputTab) {
    setActiveTab(tab);
    setGeminiError(null);
  }

  // ── Gemini generate ────────────────────────────────────────────────────────

  async function handleGenerate() {
    setGeminiError(null);
    try {
      const result = await previewMutation.mutateAsync({
        client_type: state.clientType,
        count: state.count,
      });

      // Check partial_names from successful response (shouldn't normally happen but be safe)
      const names = result.names ?? [];
      if (names.length === 0) {
        setGeminiError("Gemini tidak menghasilkan nama. Coba lagi.");
        return;
      }

      setState((s) => ({
        ...s,
        step: "review",
        names,
        groundingUrls: result.grounding_urls ?? [],
        excludedCount: result.excluded_count ?? 0,
        inputSource: "gemini",
        inputSourceLabel: "AI",
      }));
    } catch (err: unknown) {
      const errData = (
        err as {
          response?: {
            data?: {
              error_type?: string;
              partial_names?: string[];
              detail?: string;
            };
          };
        }
      )?.response?.data;
      const errorType = errData?.error_type;
      const partialNames = errData?.partial_names ?? [];

      if (partialNames.length > 0) {
        // Got some names before the error — go to review with partial results
        setState((s) => ({
          ...s,
          step: "review",
          names: partialNames,
          groundingUrls: [],
          excludedCount: 0,
          inputSource: "gemini",
          inputSourceLabel: `AI (${partialNames.length} nama parsial)`,
        }));
      } else {
        setGeminiError(getErrorMessage(errorType, errData?.detail));
      }
    }
  }

  // ── Paste proceed ──────────────────────────────────────────────────────────

  function handlePasteProceed() {
    const names = parsePasteText(pasteText);
    if (names.length === 0) return;
    setState((s) => ({
      ...s,
      step: "review",
      names,
      groundingUrls: [],
      excludedCount: 0,
      inputSource: "paste",
      inputSourceLabel: "paste",
    }));
  }

  // ── File upload ────────────────────────────────────────────────────────────

  async function handleFileChange(file: File) {
    const MAX_SIZE = 10 * 1024 * 1024; // 10 MB
    if (file.size > MAX_SIZE) {
      setUploadError("File terlalu besar. Maksimal 10 MB.");
      return;
    }
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!["xlsx", "xls", "csv"].includes(ext ?? "")) {
      setUploadError("Format tidak didukung. Gunakan .xlsx, .xls, atau .csv.");
      return;
    }

    setUploadFile(file);
    setUploadError(null);
    setUploadNames([]);
    setUploadParsing(true);
    try {
      const names = await parseFileForNames(file);
      setUploadNames(names);
    } catch {
      setUploadError("Gagal membaca file. Pastikan format Excel/CSV valid.");
    } finally {
      setUploadParsing(false);
    }
  }

  function handleUploadProceed() {
    if (uploadNames.length === 0) return;
    setState((s) => ({
      ...s,
      step: "review",
      names: uploadNames,
      groundingUrls: [],
      excludedCount: 0,
      inputSource: "upload",
      inputSourceLabel: `file: ${uploadFile?.name ?? "upload"}`,
    }));
  }

  // ── Review actions ─────────────────────────────────────────────────────────

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
        source: state.inputSource === "gemini" ? "gemini_generated" : "manual",
      });
      setState((s) => ({
        ...s,
        step: "done",
        groupId: result.group_id,
        groupName: result.group_name,
      }));
    } catch {
      // Error toast handled by mutation
    }
  }

  // ── Reset ──────────────────────────────────────────────────────────────────

  function handleReset() {
    setState(INITIAL_STATE);
    setActiveTab("gemini");
    setGeminiError(null);
    setPasteText("");
    setUploadFile(null);
    setUploadNames([]);
    setUploadError(null);
    setManualName("");
    setGroundingOpen(false);
  }

  // ── Helpers ────────────────────────────────────────────────────────────────

  const parsedPasteNames = parsePasteText(pasteText);
  const isLoadingGenerate = previewMutation.isPending;

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <Modal
      isOpen
      onClose={onClose}
      title={
        state.step === "done"
          ? "Group Berhasil Dibuat"
          : state.step === "review"
            ? "Review Nama Client"
            : "Buat Group Baru"
      }
      size="lg"
    >
      {/* ── Step: Setup ─────────────────────────────────────────────────────── */}
      {state.step === "setup" && (
        <div className="space-y-5">
          {/* Client type selector */}
          <div data-tour="modal-client-type">
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

          {/* Input method tabs */}
          <div data-tour="modal-input-tabs">
            <div className="flex gap-1 rounded-lg border border-gray-200 bg-gray-50 p-1 dark:border-gray-700 dark:bg-gray-800">
              {(
                [
                  { id: "gemini", icon: Sparkles, label: "Generate AI" },
                  { id: "paste", icon: ClipboardList, label: "Paste Nama" },
                  { id: "upload", icon: Upload, label: "Upload File" },
                ] as const
              ).map(({ id, icon: Icon, label }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => handleTabChange(id)}
                  className={cn(
                    "flex flex-1 items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    activeTab === id
                      ? "bg-white text-indigo-700 shadow-sm dark:bg-gray-700 dark:text-indigo-300"
                      : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </button>
              ))}
            </div>

            {/* Tab: Gemini ─────────────────────────────────────────────────── */}
            {activeTab === "gemini" && (
              <div data-tour="modal-gemini-area" className="mt-4 space-y-4">
                <div className="rounded-lg border border-indigo-100 bg-indigo-50 p-4 dark:border-indigo-900 dark:bg-indigo-950/30">
                  <div className="flex items-start gap-3">
                    <Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-indigo-600 dark:text-indigo-400" />
                    <div>
                      <p className="text-sm font-medium text-indigo-900 dark:text-indigo-100">
                        Generate dengan Gemini AI
                      </p>
                      <p className="mt-0.5 text-xs text-indigo-700 dark:text-indigo-300">
                        Gemini menggunakan Google Search untuk menemukan nama
                        institusi nyata. Request besar diproses dalam beberapa
                        batch otomatis.
                      </p>
                    </div>
                  </div>
                </div>

                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
                    Jumlah Nama
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
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    Minimal 5, maksimal 200. Request &gt;30 otomatis dibagi
                    beberapa batch.
                  </p>
                </div>

                {/* Inline error */}
                {geminiError && (
                  <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 dark:border-red-800 dark:bg-red-950/30">
                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-600 dark:text-red-400" />
                    <p className="text-sm text-red-700 dark:text-red-300">
                      {geminiError}
                    </p>
                  </div>
                )}

                <div className="flex justify-end gap-2">
                  <Button
                    variant="secondary"
                    onClick={onClose}
                    disabled={isLoadingGenerate}
                  >
                    Batal
                  </Button>
                  <Button
                    onClick={handleGenerate}
                    loading={isLoadingGenerate}
                    disabled={isLoadingGenerate}
                  >
                    <Sparkles className="h-4 w-4" />
                    {isLoadingGenerate ? "Generating..." : "Generate dengan AI"}
                  </Button>
                </div>
              </div>
            )}

            {/* Tab: Paste ──────────────────────────────────────────────────── */}
            {activeTab === "paste" && (
              <div className="mt-4 space-y-3">
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Paste nama client satu per baris, atau pisahkan dengan koma.
                </p>
                <textarea
                  value={pasteText}
                  onChange={(e) => setPasteText(e.target.value)}
                  rows={10}
                  placeholder={
                    "PT Telkom Indonesia\nPT Pertamina\nKementerian Keuangan\n..."
                  }
                  className="w-full rounded-lg border border-gray-300 px-3 py-2.5 font-mono text-sm
                    focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500
                    dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 dark:placeholder-gray-500"
                />
                <div className="flex items-center justify-between">
                  <span
                    className={cn(
                      "text-sm",
                      parsedPasteNames.length > 0
                        ? "text-green-600 dark:text-green-400"
                        : "text-gray-400",
                    )}
                  >
                    {parsedPasteNames.length > 0
                      ? `✓ ${parsedPasteNames.length} nama terdeteksi`
                      : "Belum ada nama"}
                  </span>
                  <div className="flex gap-2">
                    <Button variant="secondary" onClick={onClose}>
                      Batal
                    </Button>
                    <Button
                      onClick={handlePasteProceed}
                      disabled={parsedPasteNames.length === 0}
                    >
                      Lanjut ke Review →
                    </Button>
                  </div>
                </div>
              </div>
            )}

            {/* Tab: Upload ─────────────────────────────────────────────────── */}
            {activeTab === "upload" && (
              <div className="mt-4 space-y-3">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".xlsx,.xls,.csv"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleFileChange(file);
                  }}
                />

                {/* Drop zone */}
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    const file = e.dataTransfer.files?.[0];
                    if (file) handleFileChange(file);
                  }}
                  className="w-full rounded-lg border-2 border-dashed border-gray-300 p-8 text-center
                    transition-colors hover:border-indigo-400 hover:bg-indigo-50/30
                    dark:border-gray-600 dark:hover:border-indigo-500 dark:hover:bg-indigo-950/10"
                >
                  <FileSpreadsheet className="mx-auto mb-2 h-10 w-10 text-gray-400 dark:text-gray-500" />
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    {uploadFile
                      ? uploadFile.name
                      : "Drag & drop file atau klik untuk pilih"}
                  </p>
                  <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                    .xlsx, .xls, atau .csv · Maks 10 MB
                  </p>
                </button>

                {/* Parsing state */}
                {uploadParsing && (
                  <div className="flex items-center gap-2 text-sm text-gray-500">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Membaca file...
                  </div>
                )}

                {/* Parse result */}
                {uploadNames.length > 0 && !uploadParsing && (
                  <div className="flex items-center justify-between rounded-lg border border-green-200 bg-green-50 px-3 py-2 dark:border-green-800 dark:bg-green-950/20">
                    <span className="text-sm text-green-700 dark:text-green-300">
                      ✓ {uploadNames.length} nama terdeteksi dari kolom pertama
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        setUploadFile(null);
                        setUploadNames([]);
                        if (fileInputRef.current)
                          fileInputRef.current.value = "";
                      }}
                      className="ml-2 text-gray-400 hover:text-gray-600"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                )}

                {/* Upload error */}
                {uploadError && (
                  <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 dark:border-red-800 dark:bg-red-950/30">
                    <AlertCircle className="h-4 w-4 shrink-0 text-red-500" />
                    <span className="text-sm text-red-700 dark:text-red-300">
                      {uploadError}
                    </span>
                  </div>
                )}

                <p className="text-xs text-gray-400 dark:text-gray-500">
                  Kolom dengan header "nama", "company", "lembaga", atau
                  "instansi" akan otomatis terdeteksi. Jika tidak ada header,
                  kolom pertama akan dipakai.
                </p>

                <div className="flex justify-end gap-2">
                  <Button variant="secondary" onClick={onClose}>
                    Batal
                  </Button>
                  <Button
                    onClick={handleUploadProceed}
                    disabled={uploadNames.length === 0 || uploadParsing}
                  >
                    Lanjut ke Review →
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Step: Review ────────────────────────────────────────────────────── */}
      {state.step === "review" && (
        <div className="space-y-4">
          {/* Header */}
          <div className="flex items-center justify-between">
            <span className="rounded-full bg-indigo-100 px-3 py-1 text-sm font-semibold text-indigo-700 dark:bg-indigo-900 dark:text-indigo-300">
              {state.names.length} nama
            </span>
            <div className="flex items-center gap-2">
              <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-500 dark:bg-gray-700 dark:text-gray-400">
                {state.inputSourceLabel}
              </span>
              <span className="text-xs text-gray-400 dark:text-gray-500">
                {CLIENT_TYPE_LABELS[state.clientType]}
              </span>
            </div>
          </div>

          {/* Exclusion notice (Gemini only) */}
          {state.excludedCount > 0 && (
            <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                <strong>{state.excludedCount} nama</strong> sudah ada di
                database dan otomatis dikeluarkan.
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

          {/* Grounding sources (Gemini only) */}
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
              onClick={() => setState((s) => ({ ...s, step: "setup" }))}
              disabled={loadingCreate}
            >
              <ChevronLeft className="h-4 w-4" />
              Kembali
            </Button>
            <Button
              onClick={handleCreateGroup}
              loading={loadingCreate}
              disabled={loadingCreate || state.names.length === 0}
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

      {/* ── Step: Done ──────────────────────────────────────────────────────── */}
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
              Scraping pipeline sudah dimulai di background. Monitor progress di
              halaman group.
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
                  onGroupCreated?.(state.groupId!);
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
    </Modal>
  );
}
