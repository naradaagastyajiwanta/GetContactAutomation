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
 * Shows popup notifications when accounts go down, recover, or are broken on first load.
 */
export function useIGAccountHealth() {
  const prevRef = useRef<IGAccountsHealthResponse | null>(null);
  const initialPopupShownRef = useRef(false);

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

    // ── First load: show popup if accounts are already broken ──────────────
    if (!prev) {
      if (!initialPopupShownRef.current && !current.all_ok) {
        initialPopupShownRef.current = true;

        const badAccounts = current.accounts
          .filter((a) => a.status !== "connected")
          .map((a) => ({
            username: a.username,
            status: a.status as
              | "banned"
              | "disconnected"
              | "auth_limited"
              | "rate_limited"
              | "error",
          }));

        const hasBanned = badAccounts.some((a) => a.status === "banned");
        const hasDisconnected = badAccounts.some(
          (a) => a.status === "disconnected",
        );

        showIGPopup({
          id: "ig-health-initial",
          type: hasBanned || hasDisconnected ? "error" : "warning",
          title:
            current.connected === 0
              ? "Semua akun Instagram tidak aktif"
              : `${current.total - current.connected} dari ${current.total} akun Instagram bermasalah`,
          message: hasBanned
            ? "Ada akun yang diblokir oleh Instagram dan tidak bisa digunakan. Perlu diganti dengan akun baru."
            : hasDisconnected
              ? "Beberapa sesi login sudah tidak valid — perlu import ulang cookies dari browser kamu."
              : "Beberapa akun Instagram perlu perhatian. Lihat status masing-masing di bawah.",
          accounts: badAccounts,
          ctaLabel: "Perbaiki di Pengaturan Instagram",
          ctaHref: "/settings?tab=instagram&guide=1",
          duration: 0, // sticky
        });
      }
      return;
    }

    // ── Status transitions (subsequent polls) ──────────────────────────────
    const prevMap = new Map(prev.accounts.map((a) => [a.username, a.status]));

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
        recovered.push({ username: acct.username, status: "connected" });
      }
    }

    if (wentBad.length > 0) {
      const hasBanned = wentBad.some((a) => a.status === "banned");
      const hasDisconnected = wentBad.some((a) => a.status === "disconnected");

      showIGPopup({
        id: "ig-health-bad",
        type: hasBanned || hasDisconnected ? "error" : "warning",
        title: hasBanned
          ? "Ada akun Instagram yang diblokir"
          : hasDisconnected
            ? "Sesi Instagram habis"
            : "Status akun Instagram berubah",
        message: hasBanned
          ? "Instagram memblokir satu atau lebih akun kamu. Akun yang diblokir tidak bisa digunakan dan perlu diganti dengan akun baru."
          : hasDisconnected
            ? "Login sesi kamu sudah tidak valid — seperti password yang berubah atau sesi yang ditutup dari aplikasi Instagram. Perlu import ulang cookies untuk melanjutkan scraping."
            : "Beberapa akun Instagram kamu mengalami perubahan status dan mungkin tidak bisa scraping secara penuh.",
        accounts: wentBad,
        ctaLabel: "Perbaiki di Pengaturan Instagram",
        ctaHref: "/settings?tab=instagram&guide=1",
        duration: 0,
      });
    }

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

    if (prev.connected > 0 && current.connected === 0 && current.total > 0) {
      showIGPopup({
        id: "ig-all-down",
        type: "error",
        title: "Semua akun Instagram tidak aktif",
        message:
          "Tidak ada satu pun akun Instagram yang bisa digunakan saat ini. Scraping tidak bisa berjalan sampai kamu memperbaiki minimal satu akun.",
        ctaLabel: "Perbaiki di Pengaturan Instagram",
        ctaHref: "/settings?tab=instagram&guide=1",
        duration: 0,
      });
    }
  }, [query.data]);

  return query;
}
