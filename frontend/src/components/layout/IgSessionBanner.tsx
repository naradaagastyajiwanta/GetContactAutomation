import { useState, useEffect, useRef, useCallback } from "react";
import { AlertTriangle, X, ExternalLink, RefreshCw } from "lucide-react";
import { useHealth } from "../../hooks/useHealth";
import { resetIgSessions } from "../../api/health";
import { useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "../../lib/queryKeys";
import { showIGPopup } from "../../lib/igPopup";

/**
 * Global banner shown when Instagram sessions are expired or suspended.
 * Rendered in AppShell so it appears on every page.
 * Supports the multi-session pool — shows how many sessions are down.
 */
export function IgSessionBanner() {
  const { data: health } = useHealth();
  const queryClient = useQueryClient();
  const [dismissed, setDismissed] = useState(false);
  const [isExiting, setIsExiting] = useState(false);
  const [resetting, setResetting] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hoveredRef = useRef(false);

  const dismiss = useCallback(() => {
    setIsExiting(true);
    setTimeout(() => setDismissed(true), 300);
  }, []);

  const ig = health?.instagram;
  const igOk = ig?.ok ?? true;
  const total = ig?.total ?? 0;
  const healthy = ig?.healthy ?? 0;
  const sessions = ig?.sessions ?? [];
  const fallbacks = ig?.fallbacks;

  useEffect(() => {
    if (igOk || dismissed || total === 0) return;
    const startTimer = () => {
      timerRef.current = setTimeout(() => {
        if (!hoveredRef.current) dismiss();
      }, 15000);
    };
    startTimer();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [igOk, dismissed, total, dismiss]);

  // Count configured fallback providers
  const fbApify = fallbacks?.apify?.configured ?? false;
  const fbSbot = fallbacks?.scrapingbot?.configured ?? false;
  const fbCount = (fbApify ? 1 : 0) + (fbSbot ? 1 : 0);

  if (igOk || dismissed || total === 0) return null;

  const allDown = healthy === 0;
  const title = allDown
    ? total === 1
      ? "Instagram session expired"
      : `All ${total} Instagram sessions are down`
    : `${total - healthy} of ${total} IG sessions down`;

  const fallbackNote =
    allDown && fbCount > 0
      ? ` Fallback provider${fbCount > 1 ? "s" : ""} (${[fbApify && "Apify", fbSbot && "ScrapingBot"].filter(Boolean).join(", ")}) will be used automatically.`
      : "";
  const description = allDown
    ? `All IG sessions are expired or suspended.${fbCount > 0 ? fallbackNote : " Scraping agents will return empty results until you update the session IDs."}`
    : `${healthy} session(s) still active — rotation is working, but you should replace the failed session(s) soon.`;

  const handleReset = async () => {
    setResetting(true);
    try {
      await resetIgSessions();
      queryClient.invalidateQueries({ queryKey: queryKeys.health });
      showIGPopup({
        id: "ig-session-reset-ok",
        type: "success",
        title: "Sesi Instagram direset",
        message:
          "Semua sesi Instagram sudah direset dan akan dicek ulang pada request berikutnya.",
        duration: 6_000,
      });
    } catch {
      showIGPopup({
        id: "ig-session-reset-fail",
        type: "error",
        title: "Gagal mereset sesi",
        message:
          "Tidak bisa mereset sesi Instagram. Coba lagi atau periksa koneksi ke server.",
        duration: 8_000,
      });
    } finally {
      setResetting(false);
    }
  };

  return (
    <div
      onMouseEnter={() => {
        hoveredRef.current = true;
        if (timerRef.current) clearTimeout(timerRef.current);
      }}
      onMouseLeave={() => {
        hoveredRef.current = false;
        timerRef.current = setTimeout(dismiss, 5000);
      }}
      className={`${isExiting ? "animate-slide-out-right" : "animate-slide-in-right"} rounded-xl border shadow-lg backdrop-blur-sm ${
        allDown
          ? "border-red-200 bg-red-50/95 dark:border-red-800 dark:bg-red-950/90"
          : "border-amber-200 bg-amber-50/95 dark:border-amber-800 dark:bg-amber-950/90"
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 px-4 pt-3 pb-1">
        <div className="flex items-center gap-2">
          <AlertTriangle
            className={`h-4 w-4 shrink-0 ${
              allDown
                ? "text-red-500 dark:text-red-400"
                : "text-amber-500 dark:text-amber-400"
            }`}
          />
          <p
            className={`text-sm font-semibold ${
              allDown
                ? "text-red-800 dark:text-red-200"
                : "text-amber-800 dark:text-amber-200"
            }`}
          >
            {title}
          </p>
        </div>
        <button
          onClick={dismiss}
          className={`shrink-0 rounded-lg p-1 hover:bg-black/5 dark:hover:bg-white/10 ${
            allDown
              ? "text-red-400 dark:text-red-500"
              : "text-amber-400 dark:text-amber-500"
          }`}
          title="Dismiss"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Body */}
      <div className="px-4 pb-3">
        <p
          className={`text-xs leading-relaxed ${
            allDown
              ? "text-red-600 dark:text-red-300"
              : "text-amber-600 dark:text-amber-300"
          }`}
        >
          {description}
        </p>

        {/* Status pills */}
        <div className="mt-2 flex flex-wrap gap-1.5">
          {sessions.length > 1 &&
            sessions.map((s, i) => (
              <span
                key={i}
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                  s.ok
                    ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                    : "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${s.ok ? "bg-green-500" : "bg-red-500"}`}
                />
                {s.label}
                {!s.ok &&
                  s.error &&
                  ` (${s.error === "login_required" ? "expired" : s.error})`}
              </span>
            ))}
          {fbCount > 0 && allDown && fbApify && (
            <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
              <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
              Apify fallback
            </span>
          )}
          {fbCount > 0 && allDown && fbSbot && (
            <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">
              <span className="h-1.5 w-1.5 rounded-full bg-purple-500" />
              ScrapingBot fallback
            </span>
          )}
        </div>

        {/* Actions */}
        <div
          className={`mt-2 flex items-center justify-between text-xs ${
            allDown
              ? "text-red-600 dark:text-red-400"
              : "text-amber-600 dark:text-amber-400"
          }`}
        >
          <a
            href="/settings?tab=instagram"
            className="inline-flex items-center gap-1 font-medium underline hover:opacity-80"
          >
            Perbaiki di Pengaturan <ExternalLink className="h-3 w-3" />
          </a>
          <button
            onClick={handleReset}
            disabled={resetting}
            className="inline-flex items-center gap-1 rounded-md border border-current px-2 py-0.5 font-medium hover:opacity-80 disabled:opacity-50"
          >
            <RefreshCw
              className={`h-3 w-3 ${resetting ? "animate-spin" : ""}`}
            />
            Reset
          </button>
        </div>
      </div>
    </div>
  );
}
