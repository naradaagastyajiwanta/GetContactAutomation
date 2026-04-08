import type { PageTourStep } from "../hooks/usePageTour";

export const MARKETING_TOUR_STEPS: PageTourStep[] = [
  {
    element: '[data-tour="marketing-filters"]',
    popover: {
      title: "🔍 Filter Korporat",
      description:
        "Cari berdasarkan nama, filter by status pencarian kontak, tipe klien, atau yang sudah punya kontak WA/email. Kombinasikan filter untuk menemukan target yang tepat.",
      side: "bottom",
      align: "start",
    },
  },
  {
    element: '[data-tour="marketing-client-list"]',
    popover: {
      title: "🏢 Daftar Korporat",
      description:
        "Setiap baris adalah satu perusahaan target. Klik untuk lihat detail PIC yang ditemukan, hasil riset AI, dan history outreach.",
      side: "top",
      align: "start",
    },
  },
];
