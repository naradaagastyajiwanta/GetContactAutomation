import type { PageTourStep } from "../hooks/usePageTour";

export const BLAST_TOUR_STEPS: PageTourStep[] = [
  {
    element: '[data-tour="blast-new-btn"]',
    popover: {
      title: "➕ Buat Kampanye",
      description:
        "Mulai kampanye blast baru — beri nama, tulis template pesan, lalu pilih penerima dari daftar universitas atau korporat.",
      side: "bottom",
      align: "end",
    },
    permission: "blast.manage",
  },
  {
    element: '[data-tour="blast-list"]',
    popover: {
      title: "📢 Daftar Kampanye",
      description:
        "Setiap kartu menampilkan progress pengiriman, status, dan tombol kontrol (▶ Play / ⏸ Pause / ✕ Cancel). Klik kartu untuk lihat detail penerima dan log pengiriman.",
      side: "top",
      align: "start",
    },
  },
];
