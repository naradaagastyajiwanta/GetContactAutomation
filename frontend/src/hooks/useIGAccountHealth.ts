import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { showIGPopup } from "../lib/igPopup";
import {
  getIGAccountsHealth,
  type IGAccountsHealthResponse,
} from "../api/igAccounts";
import { queryKeys } from "../lib/queryKeys";

/**
 * Polls IG account health every 60s.
 * Shows popup notifications when accounts go down or recover.
 */
export function useIGAccountHealth() {
  const prevRef = useRef<IGAccountsHealthResponse | null>(null);

  const query = useQuery({
    queryKey: queryKeys.igAccountsHealth,
    queryFn: () => getIGAccountsHealth(),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: 1,
  });

  useEffect(() => {
    const current = query.data;
    if (!current || current.total === 0) return;

    const prev = prevRef.current;
    prevRef.current = current;

    // Skip first load — don't spam popups on page open
    if (!prev) return;

    const prevMap = new Map(prev.accounts.map((a) => [a.username, a.status]));

    // Collect all accounts that changed to a bad state
    type ChangedAcct = {
      username: string;
      status:
        | "banned"
        | "disconnected"
        | "auth_limited"
        | "rate_limited"
        | "connected"
        | "error";
    };
    const wentBad: ChangedAcct[] = [];
    const recovered: ChangedAcct[] = [];

    for (const acct of current.accounts) {
      const oldStatus = prevMap.get(acct.username);
      if (!oldStatus || oldStatus === acct.status) continue;

      if (oldStatus === "connected" && acct.status !== "connected") {
        wentBad.push({
          username: acct.username,
          status: acct.status as ChangedAcct["status"],
        });
      }

      if (oldStatus !== "connected" && acct.status === "connected") {
        recovered.push({
          username: acct.username,
          status: "connected",
        });
      }
    }

    // Show one aggregated popup for all accounts that went bad
    if (wentBad.length > 0) {
      const hasBanned = wentBad.some((a) => a.status === "banned");
      const hasDisconnected = wentBad.some((a) => a.status === "disconnected");

      let title: string;
      let message: string;

      if (hasBanned) {
        title = "Ada akun Instagram yang diblokir";
        message =
          "Instagram memblokir satu atau lebih akun kamu. Akun yang diblokir tidak bisa digunakan untuk scraping dan perlu diganti dengan akun baru.";
      } else if (hasDisconnected) {
        title = "Sesi Instagram habis";
        message =
          "Login sesi kamu sudah tidak valid — seperti password yang berubah atau sesi yang ditutup dari aplikasi Instagram. Perlu import ulang cookies untuk melanjutkan scraping.";
      } else {
        title = "Status akun Instagram berubah";
        message =
          "Beberapa akun Instagram kamu mengalami perubahan status dan mungkin tidak bisa scraping secara penuh. Lihat detail di bawah.";
      }

      showIGPopup({
        id: "ig-health-bad",
        type: hasBanned || hasDisconnected ? "error" : "warning",
        title,
        message,
        accounts: wentBad,
        ctaLabel: "Perbaiki di Pengaturan Instagram",
        ctaHref: "/settings?tab=instagram&guide=1",
        duration: 0, // sticky — user must close manually
      });
    }

    // Show recovery popup (auto-dismiss)
    if (recovered.length > 0) {
      showIGPopup({
        id: "ig-health-recovered",
        type: "success",
        title:
          recovered.length === 1
            ? `@${recovered[0].username} kembali terhubung`
            : `${recovered.length} akun Instagram kembali aktif`,
        message: "Scraping bisa dilanjutkan secara normal.",
        accounts: recovered,
        duration: 6_000,
      });
    }

    // All accounts down — replace existing bad popup with more urgent one
    if (prev.connected > 0 && current.connected === 0 && current.total > 0) {
      showIGPopup({
        id: "ig-all-down",
        type: "error",
        title: "Semua akun Instagram tidak aktif",
        message:
          "Tidak ada satu pun akun Instagram yang bisa digunakan saat ini. Scraping tidak bisa berjalan sampai kamu memperbaiki minimal satu akun.",
        ctaLabel: "Perbaiki di Pengaturan Instagram",
        ctaHref: "/settings?tab=instagram&guide=1",
        duration: 0, // sticky
      });
    }
  }, [query.data]);

  return query;
}
