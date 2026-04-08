import type { PageTourStep } from "../hooks/usePageTour";

export const DASHBOARD_TOUR_STEPS: PageTourStep[] = [
  {
    element: '[data-tour="dashboard-stats"]',
    popover: {
      title: "📊 Statistik Utama",
      description:
        "4 angka kunci: total universitas di database, kontak IG yang ditemukan, percakapan WA aktif, dan nomor yang berhasil didapat.",
      side: "bottom",
      align: "start",
    },
  },
  {
    element: '[data-tour="dashboard-pipeline-card"]',
    popover: {
      title: "🔀 Pipeline Funnel",
      description:
        "Lihat berapa universitas di tiap tahap — dari scraping awal hingga berhasil mendapat nomor kontak sekretariat.",
      side: "bottom",
      align: "start",
    },
  },
  {
    element: '[data-tour="dashboard-quota-card"]',
    popover: {
      title: "📅 Kuota Harian",
      description:
        "Pantau berapa pesan WA terkirim hari ini vs limit harian. Kuota di-reset setiap tengah malam WIB.",
      side: "left",
      align: "start",
    },
  },
  {
    element: '[data-tour="dashboard-audiensi-card"]',
    popover: {
      title: "🗓️ Audiensi",
      description:
        "Ringkasan antrian pertemuan formal: berapa yang menunggu konfirmasi, terjadwal, dan sudah selesai.",
      side: "top",
      align: "start",
    },
  },
];
