import { useState } from "react";
import {
  Database,
  ArrowRight,
  RefreshCw,
  Play,
  Eye,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Server,
  Users,
  Phone,
  Loader2,
  Clock,
  PlusCircle,
} from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getMigrationStatus, runMigration } from "../api/migration";
import type { MigrationJobState } from "../api/migration";

// ─── Stat Card ───────────────────────────────────────────────────────────────

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  color = "indigo",
}: {
  icon: React.ElementType;
  label: string;
  value: number | string;
  sub?: string;
  color?: "indigo" | "green" | "yellow" | "red" | "blue";
}) {
  const colors = {
    indigo:
      "bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400",
    green:
      "bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400",
    yellow:
      "bg-yellow-50 dark:bg-yellow-900/20 text-yellow-600 dark:text-yellow-400",
    red: "bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400",
    blue: "bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400",
  };
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
      <div className="flex items-center gap-3 mb-3">
        <div className={`p-2 rounded-lg ${colors[color]}`}>
          <Icon className="w-4 h-4" />
        </div>
        <span className="text-sm text-gray-500 dark:text-gray-400">
          {label}
        </span>
      </div>
      <div className="text-2xl font-bold text-gray-900 dark:text-white">
        {typeof value === "number" ? value.toLocaleString() : value}
      </div>
      {sub && <div className="text-xs text-gray-400 mt-1">{sub}</div>}
    </div>
  );
}

// ─── Job Result Panel ────────────────────────────────────────────────────────

function JobResultPanel({ job }: { job: MigrationJobState }) {
  const [showUnmatched, setShowUnmatched] = useState(false);

  if (job.job_status === "idle") return null;

  const isRunning = job.job_status === "running";
  const isDone = job.job_status === "done";
  const isError = job.job_status === "error";

  return (
    <div
      className={`rounded-xl border p-5 space-y-4 ${
        isRunning
          ? "bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800"
          : isDone
            ? "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800"
            : "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800"
      }`}
    >
      <div className="flex items-center gap-2">
        {isRunning && (
          <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
        )}
        {isDone && <CheckCircle className="w-4 h-4 text-green-500" />}
        {isError && <XCircle className="w-4 h-4 text-red-500" />}
        <span className="font-semibold text-sm">
          {isRunning &&
            `Migration${job.dry_run ? " (dry run)" : ""} sedang berjalan…`}
          {isDone && `Migration${job.dry_run ? " (dry run)" : ""} selesai`}
          {isError && "Migration gagal — lihat log server"}
        </span>
        {job.dry_run && (
          <span className="ml-auto text-xs bg-yellow-100 dark:bg-yellow-900/40 text-yellow-700 dark:text-yellow-400 px-2 py-0.5 rounded-full">
            DRY RUN
          </span>
        )}
      </div>

      {(isDone || isRunning) && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
          <div className="bg-white/60 dark:bg-black/20 rounded-lg p-3">
            <div className="text-xs text-gray-500 mb-1">
              Universitas matched
            </div>
            <div className="text-xl font-bold text-gray-800 dark:text-gray-200">
              {job.matched}
            </div>
          </div>
          <div className="bg-white/60 dark:bg-black/20 rounded-lg p-3">
            <div className="text-xs text-gray-500 mb-1">
              {job.create_missing
                ? "Tidak ditemukan (sisa)"
                : "Tidak ditemukan di MySQL"}
            </div>
            <div className="text-xl font-bold text-yellow-600 dark:text-yellow-400">
              {job.unmatched}
            </div>
          </div>
          {job.create_missing && (
            <div className="bg-white/60 dark:bg-black/20 rounded-lg p-3">
              <div className="text-xs text-gray-500 mb-1">
                {job.dry_run ? "Akan di-create" : "Di-create di MySQL"}
              </div>
              <div className="text-xl font-bold text-blue-600 dark:text-blue-400">
                {job.created ?? 0}
              </div>
            </div>
          )}
          <div className="bg-white/60 dark:bg-black/20 rounded-lg p-3">
            <div className="text-xs text-gray-500 mb-1">
              Kontak {job.dry_run ? "akan di-sync" : "di-sync"}
            </div>
            <div className="text-xl font-bold text-green-600 dark:text-green-400">
              {job.contacts_synced}
            </div>
          </div>
          <div className="bg-white/60 dark:bg-black/20 rounded-lg p-3">
            <div className="text-xs text-gray-500 mb-1">Sudah ada / error</div>
            <div className="text-xl font-bold text-gray-600 dark:text-gray-400">
              {job.contacts_skipped} / {job.contacts_errors}
            </div>
          </div>
        </div>
      )}

      {isDone && job.finished_at && (
        <div className="flex items-center gap-1.5 text-xs text-gray-500">
          <Clock className="w-3.5 h-3.5" />
          Selesai: {new Date(job.finished_at).toLocaleString("id-ID")}
        </div>
      )}

      {isDone && job.unmatched > 0 && job.unmatched_names.length > 0 && (
        <div>
          <button
            onClick={() => setShowUnmatched((v) => !v)}
            className="text-xs text-yellow-700 dark:text-yellow-400 underline underline-offset-2"
          >
            {showUnmatched ? "Sembunyikan" : "Lihat"} {job.unmatched}{" "}
            universitas yang tidak ditemukan di MySQL
          </button>
          {showUnmatched && (
            <div className="mt-2 max-h-48 overflow-y-auto rounded-lg bg-white/60 dark:bg-black/20 p-3 text-xs space-y-1">
              {job.unmatched_names.map((name) => (
                <div key={name} className="text-gray-600 dark:text-gray-400">
                  — {name}
                </div>
              ))}
              {job.unmatched > 50 && (
                <div className="text-gray-400 italic">
                  ...dan {job.unmatched - 50} lainnya
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export function DbMigrationPage() {
  const qc = useQueryClient();
  const [confirmOpen, setConfirmOpen] = useState<"run" | "dry" | null>(null);
  const [createMissing, setCreateMissing] = useState(false);

  const { data: status, isLoading } = useQuery({
    queryKey: ["migration-dms-status"],
    queryFn: getMigrationStatus,
    // Auto-poll every 2s while a job is running
    refetchInterval: (query) =>
      query.state.data?.last_job?.job_status === "running" ? 2000 : false,
  });

  const runMut = useMutation({
    mutationFn: ({ dryRun, cm }: { dryRun: boolean; cm: boolean }) =>
      runMigration(dryRun, cm),
    onSuccess: () => {
      setConfirmOpen(null);
      // Start polling
      qc.invalidateQueries({ queryKey: ["migration-dms-status"] });
    },
  });

  const dmsOk = status?.dms_status === "connected";
  const matchPct = status
    ? Math.round(
        (status.matched_universities / Math.max(status.total_universities, 1)) *
          100,
      )
    : 0;
  const jobRunning = status?.last_job?.job_status === "running";

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <Database className="w-6 h-6 text-indigo-500" />
          DB Migration
        </h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">
          Migrasi kontak universitas dari SQLite ke MySQL{" "}
          <code className="text-xs bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded">
            kontak_auto
          </code>
        </p>
      </div>

      {/* DB Info */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 space-y-3">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
          Target Database
        </h2>
        <div className="flex flex-wrap gap-3 items-center">
          <div className="flex items-center gap-2 px-3 py-2 bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600 text-sm">
            <Server className="w-3.5 h-3.5 text-gray-400" />
            <span className="text-gray-500 dark:text-gray-400 font-medium">
              SQLite:
            </span>
            <span className="font-mono text-gray-700 dark:text-gray-300">
              getcontact.db
            </span>
          </div>
          <ArrowRight className="w-4 h-4 text-gray-400" />
          <div className="flex items-center gap-2 px-3 py-2 bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600 text-sm">
            <Server className="w-3.5 h-3.5 text-gray-400" />
            <span className="text-gray-500 dark:text-gray-400 font-medium">
              MySQL:
            </span>
            <span className="font-mono text-gray-700 dark:text-gray-300">
              {status?.dms_database ?? "…"}
            </span>
            <span className="text-gray-400">@{status?.dms_host ?? "…"}</span>
          </div>
          <div className="flex items-center gap-1.5 text-sm">
            {isLoading ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin text-gray-400" />
            ) : dmsOk ? (
              <>
                <CheckCircle className="w-3.5 h-3.5 text-green-500" />
                <span className="text-green-600 dark:text-green-400">
                  Connected
                </span>
              </>
            ) : (
              <>
                <XCircle className="w-3.5 h-3.5 text-red-500" />
                <span className="text-red-600 dark:text-red-400">
                  {status?.dms_status}
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Job Result */}
      {status?.last_job && <JobResultPanel job={status.last_job} />}

      {/* Stats */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
            Status Saat Ini
          </h2>
          <button
            onClick={() =>
              qc.invalidateQueries({ queryKey: ["migration-dms-status"] })
            }
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh
          </button>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
          <StatCard
            icon={Users}
            label="Total Universitas (SQLite)"
            value={status?.total_universities ?? "—"}
            color="indigo"
          />
          <StatCard
            icon={CheckCircle}
            label="Sudah Matched ke MySQL"
            value={status?.matched_universities ?? "—"}
            sub={status ? `${matchPct}% dari total` : undefined}
            color="green"
          />
          <StatCard
            icon={AlertTriangle}
            label="Belum Matched"
            value={status?.unmatched_universities ?? "—"}
            sub="dms_univ_id belum diisi"
            color={status?.unmatched_universities ? "yellow" : "green"}
          />
          <StatCard
            icon={Phone}
            label="Kontak di SQLite"
            value={status?.total_ig_contacts ?? "—"}
            sub="ig_contacts"
            color="blue"
          />
          <StatCard
            icon={Database}
            label="Kontak di MySQL"
            value={status?.total_kontak_auto_from_ai ?? "—"}
            sub="kontak_auto (ig_scraping)"
            color="green"
          />
        </div>
      </div>

      {/* Progress bar */}
      {status && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <div className="flex justify-between text-sm mb-2">
            <span className="text-gray-600 dark:text-gray-400">
              University matching progress
            </span>
            <span className="font-semibold text-gray-800 dark:text-gray-200">
              {matchPct}%
            </span>
          </div>
          <div className="h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-indigo-500 rounded-full transition-all duration-500"
              style={{ width: `${matchPct}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-gray-400 mt-1">
            <span>{status.matched_universities} matched</span>
            <span>{status.total_universities} total</span>
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 space-y-4">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
          Jalankan Migrasi
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Ambil semua{" "}
          <code className="text-xs bg-gray-100 dark:bg-gray-700 px-1 rounded">
            ig_contacts
          </code>{" "}
          dari SQLite → match universitas → insert ke{" "}
          <code className="text-xs bg-gray-100 dark:bg-gray-700 px-1 rounded">
            kontak_auto
          </code>
          . Duplikat dilewati otomatis.
        </p>

        {/* Option: auto-create missing */}
        <label className="flex items-start gap-2.5 cursor-pointer group">
          <input
            type="checkbox"
            checked={createMissing}
            onChange={(e) => setCreateMissing(e.target.checked)}
            disabled={jobRunning}
            className="mt-0.5 h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
          />
          <div>
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300 flex items-center gap-1.5">
              <PlusCircle className="w-3.5 h-3.5 text-blue-500" />
              Auto-create universitas yang tidak ditemukan
            </span>
            <p className="text-xs text-gray-400 mt-0.5">
              Jika universitas tidak ada di MySQL{" "}
              <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">
                universitas
              </code>
              , otomatis INSERT baru dengan nama dari SQLite. Aktifkan hanya
              jika yakin tidak ada duplikat.
            </p>
          </div>
        </label>

        <div className="flex flex-wrap gap-3">
          {confirmOpen === "dry" ? (
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-600 dark:text-gray-400">
                Jalankan dry-run{createMissing ? " + auto-create" : ""}?
              </span>
              <button
                onClick={() =>
                  runMut.mutate({ dryRun: true, cm: createMissing })
                }
                disabled={runMut.isPending || jobRunning}
                className="px-3 py-1.5 bg-yellow-500 hover:bg-yellow-600 text-white text-sm rounded-lg font-medium transition-colors disabled:opacity-50"
              >
                {runMut.isPending ? "Starting…" : "Ya, lanjut"}
              </button>
              <button
                onClick={() => setConfirmOpen(null)}
                className="px-3 py-1.5 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-sm rounded-lg font-medium"
              >
                Batal
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmOpen("dry")}
              disabled={runMut.isPending || jobRunning || !dmsOk}
              className="flex items-center gap-2 px-4 py-2.5 bg-yellow-50 hover:bg-yellow-100 dark:bg-yellow-900/20 dark:hover:bg-yellow-900/40 text-yellow-700 dark:text-yellow-400 border border-yellow-200 dark:border-yellow-800 text-sm font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Eye className="w-4 h-4" />
              Dry Run (Preview saja)
            </button>
          )}

          {confirmOpen === "run" ? (
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-red-600 dark:text-red-400">
                Akan menulis ke <strong>{status?.dms_database}</strong>
                {createMissing && " + create universitas baru"}. Lanjut?
              </span>
              <button
                onClick={() =>
                  runMut.mutate({ dryRun: false, cm: createMissing })
                }
                disabled={runMut.isPending || jobRunning}
                className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm rounded-lg font-medium transition-colors disabled:opacity-50"
              >
                {runMut.isPending ? "Starting…" : "Ya, migrasi sekarang"}
              </button>
              <button
                onClick={() => setConfirmOpen(null)}
                className="px-3 py-1.5 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-sm rounded-lg font-medium"
              >
                Batal
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmOpen("run")}
              disabled={runMut.isPending || jobRunning || !dmsOk}
              className="flex items-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {jobRunning ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Running…
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  Jalankan Migrasi
                </>
              )}
            </button>
          )}
        </div>

        {!dmsOk && status && (
          <p className="text-xs text-red-500 flex items-center gap-1">
            <XCircle className="w-3.5 h-3.5" />
            Koneksi MySQL gagal — periksa env DMS_MYSQL_*
          </p>
        )}
      </div>
    </div>
  );
}
