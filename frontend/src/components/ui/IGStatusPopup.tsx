import { useState, useEffect } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  X,
  ArrowRight,
} from "lucide-react";
import {
  subscribeIGPopup,
  dismissIGPopup,
  type IGPopupConfig,
  type IGPopupAccount,
} from "../../lib/igPopup";

// ── Per-status human-readable labels ────────────────────────────────────────

const STATUS_META: Record<
  string,
  { label: string; textClass: string; dotClass: string }
> = {
  banned: {
    label: "Diblokir Instagram — akun tidak bisa digunakan lagi",
    textClass: "text-red-700 dark:text-red-400",
    dotClass: "bg-red-500",
  },
  disconnected: {
    label: "Sesi habis masa berlaku — perlu login ulang",
    textClass: "text-red-600 dark:text-red-400",
    dotClass: "bg-red-500",
  },
  auth_limited: {
    label: "Akses dibatasi — hanya bisa lihat profil publik",
    textClass: "text-amber-700 dark:text-amber-400",
    dotClass: "bg-amber-500",
  },
  rate_limited: {
    label: "Istirahat sementara — akan aktif kembali otomatis",
    textClass: "text-amber-600 dark:text-amber-400",
    dotClass: "bg-amber-400",
  },
  connected: {
    label: "Terhubung dan aktif",
    textClass: "text-green-600 dark:text-green-400",
    dotClass: "bg-green-500",
  },
  error: {
    label: "Terjadi kesalahan tidak terduga",
    textClass: "text-gray-600 dark:text-gray-400",
    dotClass: "bg-gray-400",
  },
};

// ── Account pill ─────────────────────────────────────────────────────────────

function AccountPill({ acct }: { acct: IGPopupAccount }) {
  const meta = STATUS_META[acct.status] ?? STATUS_META.error;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs font-medium dark:border-gray-700 dark:bg-gray-800 ${meta.textClass}`}
    >
      <span
        className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${meta.dotClass}`}
      />
      <span className="font-semibold">@{acct.username}</span>
      <span className="opacity-60">— {meta.label}</span>
    </span>
  );
}

// ── Single popup card ─────────────────────────────────────────────────────────

const TYPE_CONFIG = {
  success: {
    icon: CheckCircle2,
    iconClass: "text-green-500",
    headerBg: "bg-green-50 dark:bg-green-950/50",
    border: "border-green-200 dark:border-green-800",
    titleClass: "text-green-900 dark:text-green-100",
    ctaBg: "bg-green-600 hover:bg-green-700",
  },
  warning: {
    icon: AlertTriangle,
    iconClass: "text-amber-500",
    headerBg: "bg-amber-50 dark:bg-amber-950/50",
    border: "border-amber-200 dark:border-amber-800",
    titleClass: "text-amber-900 dark:text-amber-100",
    ctaBg: "bg-indigo-600 hover:bg-indigo-700",
  },
  error: {
    icon: XCircle,
    iconClass: "text-red-500",
    headerBg: "bg-red-50 dark:bg-red-950/50",
    border: "border-red-200 dark:border-red-800",
    titleClass: "text-red-900 dark:text-red-100",
    ctaBg: "bg-indigo-600 hover:bg-indigo-700",
  },
};

function PopupCard({
  config,
  onDismiss,
}: {
  config: IGPopupConfig;
  onDismiss: () => void;
}) {
  const cfg = TYPE_CONFIG[config.type];
  const Icon = cfg.icon;

  return (
    <div
      className={`animate-slide-in-right w-full overflow-hidden rounded-2xl border bg-white shadow-2xl dark:bg-gray-900 ${cfg.border}`}
    >
      {/* Header */}
      <div
        className={`flex items-start justify-between gap-3 px-4 py-3 ${cfg.headerBg}`}
      >
        <div className="flex items-center gap-2.5">
          <Icon className={`h-5 w-5 flex-shrink-0 ${cfg.iconClass}`} />
          <p className={`text-sm font-semibold ${cfg.titleClass}`}>
            {config.title}
          </p>
        </div>
        <button
          onClick={onDismiss}
          className="flex-shrink-0 rounded-lg p-1 text-gray-400 transition-colors hover:bg-black/5 hover:text-gray-600 dark:hover:bg-white/10 dark:hover:text-gray-300"
          title="Tutup"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Body */}
      <div className="space-y-3 px-4 py-3">
        <p className="text-sm leading-relaxed text-gray-600 dark:text-gray-300">
          {config.message}
        </p>

        {/* Account status pills */}
        {config.accounts && config.accounts.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {config.accounts.map((acct) => (
              <AccountPill key={acct.username} acct={acct} />
            ))}
          </div>
        )}

        {/* CTA button */}
        {config.ctaLabel && config.ctaHref && (
          <a
            href={config.ctaHref}
            className={`mt-1 flex w-full items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold text-white transition-colors ${cfg.ctaBg}`}
          >
            {config.ctaLabel}
            <ArrowRight className="h-4 w-4" />
          </a>
        )}
      </div>
    </div>
  );
}

// ── Root component (mount once in AppShell) ───────────────────────────────────

export function IGStatusPopup() {
  const [popups, setPopups] = useState<IGPopupConfig[]>([]);

  useEffect(() => {
    return subscribeIGPopup(setPopups);
  }, []);

  if (popups.length === 0) return null;

  return (
    <div className="fixed right-4 top-4 z-[70] flex w-full max-w-sm flex-col gap-2">
      {popups.map((popup) => (
        <PopupCard
          key={popup.id}
          config={popup}
          onDismiss={() => dismissIGPopup(popup.id)}
        />
      ))}
    </div>
  );
}
