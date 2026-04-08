import type { PageTourStep } from "../hooks/usePageTour";

export const MARKETING_GROUP_DETAIL_TOUR_STEPS: PageTourStep[] = [
  {
    element: '[data-tour="group-detail-header"]',
    popover: {
      title: "📋 Info Grup",
      description:
        "Nama grup, tipe korporat, dan status pencarian: <b>Draft</b> (belum mulai), <b>Searching</b> (AI sedang bekerja), atau <b>Done</b> (selesai).",
    },
  },
  {
    element: '[data-tour="group-detail-actions"]',
    popover: {
      title: "▶ Mulai Scraping",
      description:
        "Tekan <b>Mulai Scraping</b> untuk mengaktifkan AI agent — agent akan mencari kontak WhatsApp & email dari setiap perusahaan di grup ini secara otomatis.",
      side: "bottom",
    },
    permission: "marketing.manage",
  },
  {
    element: '[data-tour="group-detail-stats"]',
    popover: {
      title: "📊 Statistik Pencarian",
      description:
        "<b>Total</b> — jumlah klien di grup. <b>Ditemukan</b> — kontak berhasil ditemukan. <b>Pending</b> — masih diproses. <b>Approved</b> — sudah siap di-blast.",
      side: "bottom",
    },
  },
  {
    element: '[data-tour="group-detail-clients"]',
    popover: {
      title: "🏢 Daftar Klien",
      description:
        "Setiap baris adalah satu perusahaan target. Klik baris untuk lihat kontak yang ditemukan, approve kontak, atau lihat detail profil perusahaan.",
      side: "top",
    },
  },
];
