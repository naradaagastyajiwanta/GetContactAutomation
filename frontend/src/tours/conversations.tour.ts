import type { PageTourStep } from "../hooks/usePageTour";

export const CONVERSATIONS_TOUR_STEPS: PageTourStep[] = [
  {
    element: '[data-tour="conversations-filters"]',
    popover: {
      title: "🔽 Filter Percakapan",
      description:
        "Filter by status percakapan: PENDING (belum dibalas), WAITING_REPLY, REPLIED, GOT_NUMBER, REFUSED, dll. Fokus ke percakapan yang butuh perhatian.",
      side: "bottom",
      align: "end",
    },
  },
  {
    element: '[data-tour="conversations-list"]',
    popover: {
      title: "💬 Daftar Percakapan",
      description:
        "Setiap baris adalah satu percakapan WhatsApp dengan kontak universitas. Klik untuk buka riwayat pesan lengkap dan lihat analisis AI.",
      side: "top",
      align: "start",
    },
  },
];
