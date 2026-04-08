import type { PageTourStep } from "../hooks/usePageTour";

export const PIPELINE_TOUR_STEPS: PageTourStep[] = [
  {
    element: '[data-tour="pipeline-stage-stats"]',
    popover: {
      title: "📈 Stage Overview",
      description:
        "Angka real-time di tiap tahap pipeline: Pending → IG Found → IG Scraped → Contacted → Got Number. Semakin banyak di kanan, semakin sukses.",
      side: "bottom",
      align: "start",
    },
  },
  {
    element: '[data-tour="pipeline-agents"]',
    popover: {
      title: "🤖 Trigger Agents",
      description:
        "Klik kartu untuk menjalankan agent secara manual. Setiap agent menangani satu tahap pipeline — dari cari handle IG hingga ekstrak nomor dari foto.",
      side: "bottom",
      align: "start",
      // operator+ only — viewers can see but not click
    },
  },
  {
    element: '[data-tour="pipeline-activity-log"]',
    popover: {
      title: "📋 Activity Log",
      description:
        "Riwayat semua agent yang dijalankan beserta hasilnya. Klik baris untuk lihat detail — berapa sukses, berapa gagal, dan pesan error jika ada.",
      side: "top",
      align: "start",
    },
  },
];
