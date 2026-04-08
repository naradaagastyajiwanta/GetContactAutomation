import type { PageTourStep } from "../hooks/usePageTour";

export const MARKETING_GROUPS_TOUR_STEPS: PageTourStep[] = [
  {
    element: '[data-tour="mktg-header"]',
    popover: {
      title: "📣 Marketing Groups",
      description:
        "Halaman ini untuk mengelola grup target outreach — setiap grup berisi daftar perusahaan yang akan dicari kontak WhatsApp & email-nya oleh AI agent.",
    },
  },
  {
    element: '[data-tour="mktg-create-btn"]',
    popover: {
      title: "➕ Buat Grup Baru",
      description:
        "Tombol ini untuk membuat grup target baru. Klik <b>Selesai ✓</b> untuk menutup panduan ini, lalu <b>klik tombol Buat Group</b> yang akan berkedip untuk memulai.",
      side: "bottom",
      align: "end",
    },
    permission: "marketing.manage",
  },
  {
    element: '[data-tour="mktg-type-filter"]',
    popover: {
      title: "🏷️ Filter Tipe",
      description:
        "Filter grup berdasarkan tipe industri: Kementerian, BUMN, Swasta, Asosiasi, dll.",
    },
  },
  {
    element: '[data-tour="mktg-group-list"]',
    popover: {
      title: "📋 Daftar Grup",
      description:
        "Setiap kartu adalah satu grup target. <strong>Klik salah satu grup</strong> untuk masuk ke halaman detail — di sana kamu bisa mulai scraping kontak, lihat statistik, dan kelola klien per grup.",
    },
  },
];
