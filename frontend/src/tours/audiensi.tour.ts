import type { PageTourStep } from "../hooks/usePageTour";

export const AUDIENSI_TOUR_STEPS: PageTourStep[] = [
  {
    element: '[data-tour="audiensi-tabs"]',
    popover: {
      title: "📑 3 Tab Audiensi",
      description:
        "<b>Pending Approval</b> — perlu dikonfirmasi sebelum dikirim.<br><b>All Conversations</b> — semua riwayat audiensi.<br><b>Template Surat</b> — upload template surat resmi PDF.",
      side: "bottom",
      align: "start",
    },
  },
  {
    element: '[data-tour="audiensi-content"]',
    popover: {
      title: "✅ Approval Queue",
      description:
        "Setiap card adalah permintaan audiensi yang menunggu persetujuan. Review dan approve sebelum surat dikirimkan ke universitas.",
      side: "top",
      align: "start",
    },
  },
];
