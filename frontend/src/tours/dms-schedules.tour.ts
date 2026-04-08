import type { PageTourStep } from "../hooks/usePageTour";

export const DMS_SCHEDULES_TOUR_STEPS: PageTourStep[] = [
  {
    element: '[data-tour="dms-actions"]',
    popover: {
      title: "🔄 Sinkronisasi DMS",
      description:
        "Sync data dari sistem DMS eksternal untuk memperbarui jadwal audiensi, status, dan link Zoom terbaru.",
    },
  },
  {
    element: '[data-tour="dms-stats"]',
    popover: {
      title: "📊 Statistik Jadwal",
      description:
        "Ringkasan total jadwal, berapa yang pending, dikonfirmasi, dan selesai.",
    },
  },
  {
    element: '[data-tour="dms-tabs"]',
    popover: {
      title: "📑 Filter Status",
      description:
        "Filter jadwal berdasarkan status: semua, pending konfirmasi, atau sudah selesai.",
    },
  },
];
