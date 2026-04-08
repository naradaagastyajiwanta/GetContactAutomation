/**
 * WaBlastPanel Component
 *
 * Powerful blast panel: paste or file-upload numbers, text or document mode,
 * number parsing/deduplication, live queue progress polling.
 */

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import {
  Send,
  FileText,
  Upload,
  ClipboardList,
  Loader2,
  CheckCircle,
  RefreshCw,
  X,
  ChevronDown,
} from "lucide-react";
import {
  useMyDevices,
  useWhatsAppDevices,
  useBulkSendWhatsApp,
  useBulkSendDocumentWhatsApp,
} from "../../hooks/useWhatsApp";
import { useAuth } from "../../context/AuthContext";
import { cn } from "../../lib/utils";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseNumbers(raw: string): { valid: string[]; invalid: number } {
  const lines = raw
    .split(/[\n,;]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const valid: string[] = [];
  const seen = new Set<string>();
  let invalid = 0;

  for (const line of lines) {
    const digits = line.replace(/\D/g, "");
    let normalized = digits;

    if (digits.startsWith("08")) {
      normalized = "62" + digits.slice(1);
    } else if (
      digits.startsWith("8") &&
      digits.length >= 9 &&
      digits.length <= 12
    ) {
      normalized = "62" + digits;
    }
    // else: keep as-is — could be any valid international format (1xxx, 44xxx, etc.)

    // Validate E.164 length: 7–15 digits
    if (normalized.length < 7 || normalized.length > 15) {
      invalid++;
      continue;
    }

    if (seen.has(normalized)) continue;
    seen.add(normalized);
    valid.push(normalized);
  }

  return { valid, invalid };
}

async function parseFile(file: File): Promise<string> {
  const text = await file.text();
  if (file.name.endsWith(".csv")) {
    return text
      .split("\n")
      .flatMap((line) => line.split(/[,;\t]/))
      .filter((cell) => /\d{8,}/.test(cell.replace(/\D/g, "")))
      .join("\n");
  }
  return text;
}

function estimatedMinutes(count: number): string {
  const minutes = Math.ceil((count * 8) / 60);
  return minutes < 1 ? "<1" : String(minutes);
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

type InputMode = "paste" | "upload";
type SendMode = "text" | "document";

interface QueueStats {
  pending: number;
  sent: number;
  failed: number;
}

export function WaBlastPanel() {
  const { hasPermission } = useAuth();
  const isAdmin = hasPermission("*");

  const { data: myDevicesData } = useMyDevices();
  const { data: allDevicesData } = useWhatsAppDevices(isAdmin);
  const bulkSendMutation = useBulkSendWhatsApp();
  const bulkSendDocMutation = useBulkSendDocumentWhatsApp();

  const [inputMode, setInputMode] = useState<InputMode>("paste");
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>("");
  const [numbers, setNumbers] = useState<string[]>([]);
  const [rawPaste, setRawPaste] = useState<string>("");
  const [invalidCount, setInvalidCount] = useState<number>(0);
  const [message, setMessage] = useState<string>("");
  const [mode, setMode] = useState<SendMode>("text");
  const [filePath, setFilePath] = useState<string>("");
  const [fileName, setFileName] = useState<string>("");
  const [caption, setCaption] = useState<string>("");
  const [uploadedFileName, setUploadedFileName] = useState<string>("");
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [isSent, setIsSent] = useState<boolean>(false);
  const [sentCount, setSentCount] = useState<number>(0);
  const [queueStats, setQueueStats] = useState<QueueStats | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // All devices (not just connected) for the dropdown.
  // Admins see all system devices; non-admins see only their personal devices.
  // Memoized so the auto-select effect has a stable dependency.
  const allDevices = useMemo(
    () =>
      isAdmin
        ? (allDevicesData?.devices || []).map((d) => ({
            id: d.id,
            name: d.name,
            phoneNumber: d.phoneNumber,
            connected: d.connectionState === "connected",
          }))
        : (myDevicesData?.devices || []).map((e) => ({
            id: e.device_id,
            name: e.label || e.device?.name || e.device_id,
            phoneNumber: e.device?.phoneNumber ?? null,
            connected: e.device?.connectionState === "connected",
          })),
    [isAdmin, allDevicesData, myDevicesData],
  );

  const hasDevices = allDevices.length > 0;
  const selectedDevice = allDevices.find((d) => d.id === selectedDeviceId);
  const isSelectedConnected = selectedDevice?.connected ?? false;

  // Auto-select first connected device on mount / when devices load
  useEffect(() => {
    if (selectedDeviceId || allDevices.length === 0) return;
    const connected = allDevices.find((d) => d.connected);
    setSelectedDeviceId(connected ? connected.id : allDevices[0].id);
  }, [allDevices, selectedDeviceId]);

  // Extract live queue stats from the selected device's data
  useEffect(() => {
    if (!isSent) return;
    let stats: QueueStats | undefined;
    if (isAdmin) {
      const deviceEntry = allDevicesData?.devices.find(
        (d) => d.id === selectedDeviceId,
      );
      stats = (deviceEntry as any)?.queueStats as QueueStats | undefined;
    } else {
      const deviceEntry = myDevicesData?.devices.find(
        (e) => e.device_id === selectedDeviceId,
      );
      stats = (deviceEntry?.device as any)?.queueStats as
        | QueueStats
        | undefined;
    }
    if (stats) setQueueStats(stats);
  }, [myDevicesData, allDevicesData, isSent, selectedDeviceId, isAdmin]);

  // Parse paste input
  const handlePasteChange = (raw: string) => {
    setRawPaste(raw);
    const { valid, invalid } = parseNumbers(raw);
    setNumbers(valid);
    setInvalidCount(invalid);
  };

  // File drop / select
  const handleFileSelect = useCallback(async (file: File) => {
    setUploadedFileName(file.name);
    const raw = await parseFile(file);
    const { valid, invalid } = parseNumbers(raw);
    setNumbers(valid);
    setInvalidCount(invalid);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFileSelect(file);
    },
    [handleFileSelect],
  );

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFileSelect(file);
  };

  const resetUpload = () => {
    setUploadedFileName("");
    setNumbers([]);
    setInvalidCount(0);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const isSending = bulkSendMutation.isPending || bulkSendDocMutation.isPending;

  const canSubmit =
    numbers.length > 0 &&
    !!selectedDeviceId &&
    isSelectedConnected &&
    (mode === "text"
      ? message.trim().length > 0
      : filePath.trim().length > 0 && fileName.trim().length > 0);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;

    if (mode === "text") {
      bulkSendMutation.mutate(
        {
          phone_numbers: numbers,
          message: message.trim(),
          device_id: selectedDeviceId,
        },
        {
          onSuccess: () => {
            setIsSent(true);
            setSentCount(numbers.length);
          },
        },
      );
    } else {
      bulkSendDocMutation.mutate(
        {
          phone_numbers: numbers,
          file_path: filePath.trim(),
          file_name: fileName.trim(),
          caption: caption.trim() || undefined,
          device_id: selectedDeviceId,
        },
        {
          onSuccess: () => {
            setIsSent(true);
            setSentCount(numbers.length);
          },
        },
      );
    }
  };

  const handleReset = () => {
    setIsSent(false);
    setSentCount(0);
    setQueueStats(null);
    setNumbers([]);
    setRawPaste("");
    setInvalidCount(0);
    setUploadedFileName("");
    setMessage("");
    setFilePath("");
    setFileName("");
    setCaption("");
  };

  // Progress calculation
  const progressTotal =
    queueStats != null
      ? queueStats.pending + queueStats.sent + queueStats.failed
      : sentCount;
  const progressDone = queueStats?.sent ?? 0;
  const progressPct =
    progressTotal > 0 ? Math.round((progressDone / progressTotal) * 100) : 0;

  // ---------------------------------------------------------------------------
  // POST-SEND: progress view
  // ---------------------------------------------------------------------------
  if (isSent) {
    return (
      <div className="space-y-5">
        {/* Success header */}
        <div className="flex items-center gap-3 p-4 rounded-xl bg-green-50 dark:bg-green-900/15 border border-green-200 dark:border-green-800">
          <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400 flex-shrink-0" />
          <div>
            <p className="text-sm font-semibold text-green-800 dark:text-green-300">
              {sentCount} pesan berhasil di-queue
            </p>
            <p className="text-xs text-green-700 dark:text-green-400 mt-0.5">
              Dikirim ke device:{" "}
              <span className="font-mono">
                {selectedDevice?.name ?? selectedDeviceId}
              </span>
            </p>
          </div>
        </div>

        {/* Progress bar */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
              Progress Pengiriman
            </span>
            <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">
              {progressPct}%
            </span>
          </div>
          <div className="w-full h-2.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-green-500 rounded-full transition-all duration-700"
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>

        {/* Stats row */}
        {queueStats != null && (
          <div className="grid grid-cols-3 gap-3">
            <div className="text-center p-3 rounded-xl bg-gray-50 dark:bg-gray-900/50 border border-gray-100 dark:border-gray-700">
              <p className="text-lg font-bold text-amber-600 dark:text-amber-400">
                {queueStats.pending}
              </p>
              <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
                pending
              </p>
            </div>
            <div className="text-center p-3 rounded-xl bg-gray-50 dark:bg-gray-900/50 border border-gray-100 dark:border-gray-700">
              <p className="text-lg font-bold text-green-600 dark:text-green-400">
                {queueStats.sent}
              </p>
              <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
                terkirim
              </p>
            </div>
            <div className="text-center p-3 rounded-xl bg-gray-50 dark:bg-gray-900/50 border border-gray-100 dark:border-gray-700">
              <p className="text-lg font-bold text-red-600 dark:text-red-400">
                {queueStats.failed}
              </p>
              <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
                gagal
              </p>
            </div>
          </div>
        )}

        {/* Note */}
        <p className="text-[11px] text-gray-400 dark:text-gray-500 text-center leading-relaxed">
          Pesan dikirim dengan delay anti-ban. Refresh otomatis tiap 5 detik.
        </p>

        {/* Reset */}
        <button
          type="button"
          onClick={handleReset}
          className="flex items-center justify-center gap-2 w-full px-4 py-2.5 rounded-xl border-2 border-dashed border-gray-300 dark:border-gray-600 text-sm font-semibold text-gray-600 dark:text-gray-400 hover:border-blue-400 hover:text-blue-600 dark:hover:border-blue-500 dark:hover:text-blue-400 transition-all"
        >
          <RefreshCw className="w-4 h-4" />
          Blast Baru
        </button>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // MAIN FORM
  // ---------------------------------------------------------------------------
  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {/* ── Device Selector ─────────────────────────────────── */}
      <div>
        <label className="block text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-1.5">
          Device <span className="text-red-400">*</span>
        </label>
        {!hasDevices ? (
          <div className="flex items-center gap-2.5 p-3 rounded-lg bg-amber-50 dark:bg-amber-900/15 border border-amber-200 dark:border-amber-800">
            <span className="text-amber-500 text-sm">!</span>
            <p className="text-xs text-amber-700 dark:text-amber-300">
              Setup WA device dulu di tab Devices
            </p>
          </div>
        ) : (
          <div className="relative">
            <select
              value={selectedDeviceId}
              onChange={(e) => setSelectedDeviceId(e.target.value)}
              className="w-full appearance-none px-3 py-2 pr-8 border border-gray-300 dark:border-gray-600 rounded-xl text-sm focus:ring-1 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-900 dark:text-gray-100 transition-colors"
            >
              {allDevices.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.connected ? "● " : "○ "}
                  {d.name}
                  {d.phoneNumber ? ` (${d.phoneNumber})` : ""}
                  {d.connected ? "" : " — offline"}
                </option>
              ))}
            </select>
            <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          </div>
        )}
        {selectedDeviceId && !isSelectedConnected && (
          <p className="mt-1.5 text-xs text-amber-600 dark:text-amber-400">
            Device ini offline — hubungkan dulu di tab Devices
          </p>
        )}
      </div>

      {/* ── Mode toggle: Text | Document ────────────────────── */}
      <div className="inline-flex rounded-lg bg-gray-100 dark:bg-gray-900 p-0.5">
        <button
          type="button"
          onClick={() => setMode("text")}
          className={cn(
            "flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-semibold transition-all",
            mode === "text"
              ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm"
              : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300",
          )}
        >
          <Send className="w-3.5 h-3.5" />
          Text Message
        </button>
        <button
          type="button"
          onClick={() => setMode("document")}
          className={cn(
            "flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-semibold transition-all",
            mode === "document"
              ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm"
              : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300",
          )}
        >
          <FileText className="w-3.5 h-3.5" />
          Document
        </button>
      </div>

      {/* ── Nomor Tujuan ─────────────────────────────────────── */}
      <div>
        <label className="block text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-2">
          Nomor Tujuan <span className="text-red-400">*</span>
        </label>

        {/* Input mode tab toggle */}
        <div className="flex gap-1 mb-3">
          <button
            type="button"
            onClick={() => {
              setInputMode("paste");
              resetUpload();
            }}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all",
              inputMode === "paste"
                ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300"
                : "border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:border-gray-300 dark:hover:border-gray-600",
            )}
          >
            <ClipboardList className="w-3.5 h-3.5" />
            Paste
          </button>
          <button
            type="button"
            onClick={() => {
              setInputMode("upload");
              setRawPaste("");
              setNumbers([]);
              setInvalidCount(0);
            }}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all",
              inputMode === "upload"
                ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300"
                : "border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:border-gray-300 dark:hover:border-gray-600",
            )}
          >
            <Upload className="w-3.5 h-3.5" />
            Upload File
          </button>
        </div>

        {/* Paste mode */}
        {inputMode === "paste" && (
          <textarea
            value={rawPaste}
            onChange={(e) => handlePasteChange(e.target.value)}
            rows={5}
            placeholder={
              "Satu nomor per baris, contoh:\n6281234567890\n6289876543210\n14155552671\n\nFormat: internasional (62xxx, 1xxx, 44xxx) atau lokal (08xxx)"
            }
            className="w-full px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-xl text-sm font-mono focus:ring-1 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-900 dark:text-gray-100 transition-colors resize-none"
          />
        )}

        {/* Upload mode */}
        {inputMode === "upload" && (
          <div>
            {uploadedFileName ? (
              <div className="flex items-center justify-between px-4 py-3 rounded-xl border border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/15">
                <div className="flex items-center gap-2.5">
                  <FileText className="w-4 h-4 text-green-600 dark:text-green-400" />
                  <div>
                    <p className="text-sm font-semibold text-green-800 dark:text-green-300">
                      {uploadedFileName}
                    </p>
                    <p className="text-xs text-green-600 dark:text-green-400">
                      {numbers.length} nomor ditemukan
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={resetUpload}
                  className="p-1 rounded-lg hover:bg-green-100 dark:hover:bg-green-900/30 transition-colors"
                >
                  <X className="w-4 h-4 text-green-700 dark:text-green-400" />
                </button>
              </div>
            ) : (
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsDragging(true);
                }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={cn(
                  "flex flex-col items-center justify-center gap-2 px-4 py-8 rounded-xl border-2 border-dashed cursor-pointer transition-all",
                  isDragging
                    ? "border-blue-500 bg-blue-50 dark:bg-blue-900/15"
                    : "border-gray-300 dark:border-gray-600 hover:border-blue-400 dark:hover:border-blue-500 hover:bg-gray-50 dark:hover:bg-gray-800/50",
                )}
              >
                <Upload
                  className={cn(
                    "w-7 h-7 transition-colors",
                    isDragging
                      ? "text-blue-500"
                      : "text-gray-400 dark:text-gray-500",
                  )}
                />
                <div className="text-center">
                  <p className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                    Drop file .txt atau .csv di sini
                  </p>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                    atau klik untuk pilih file
                  </p>
                </div>
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,.csv"
              className="hidden"
              onChange={handleFileInputChange}
            />
          </div>
        )}
      </div>

      {/* ── Preview Bar ─────────────────────────────────────── */}
      {numbers.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400">
            <CheckCircle className="w-3.5 h-3.5" />
            {numbers.length} nomor valid
          </span>
          {invalidCount > 0 && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400">
              {invalidCount} dilewati (format salah)
            </span>
          )}
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400">
            Est. waktu: ~{estimatedMinutes(numbers.length)} menit
          </span>
        </div>
      )}

      {/* ── Pesan (text mode) ───────────────────────────────── */}
      {mode === "text" && (
        <div>
          <label className="block text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-1.5">
            Pesan <span className="text-red-400">*</span>
          </label>
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={5}
            placeholder={
              "Tulis pesan blast kamu di sini...\n\nTip: gunakan {nama} untuk personalisasi (jika CSV punya kolom nama)"
            }
            className="w-full px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-xl text-sm focus:ring-1 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-900 dark:text-gray-100 transition-colors resize-none"
          />
        </div>
      )}

      {/* ── Dokumen (document mode) ─────────────────────────── */}
      {mode === "document" && (
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-1.5">
              File Path <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={filePath}
              onChange={(e) => setFilePath(e.target.value)}
              placeholder="/path/to/document.pdf"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-xl font-mono text-sm focus:ring-1 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-900 dark:text-gray-100 transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-1.5">
              File Name <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={fileName}
              onChange={(e) => setFileName(e.target.value)}
              placeholder="document.pdf"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-xl text-sm focus:ring-1 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-900 dark:text-gray-100 transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-1.5">
              Caption{" "}
              <span className="text-gray-400 normal-case font-normal">
                (optional)
              </span>
            </label>
            <textarea
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              rows={2}
              placeholder="Optional caption..."
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-xl text-sm focus:ring-1 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-900 dark:text-gray-100 transition-colors resize-none"
            />
          </div>
        </div>
      )}

      {/* ── Footer ──────────────────────────────────────────── */}
      <div className="flex items-center justify-end pt-4 border-t border-gray-100 dark:border-gray-700">
        <button
          type="submit"
          disabled={!canSubmit || isSending}
          className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-xl shadow-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSending ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Queuing...
            </>
          ) : (
            <>
              <Send className="w-4 h-4" />
              {numbers.length > 0
                ? `Kirim ${numbers.length} Pesan`
                : "Kirim Pesan"}
            </>
          )}
        </button>
      </div>
    </form>
  );
}

// Keep old name exported for any lingering direct imports
export { WaBlastPanel as BulkSendPanel };
