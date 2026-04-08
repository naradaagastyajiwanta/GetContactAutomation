import type { PageTourStep } from "../hooks/usePageTour";

export const MARKETING_GROUPS_TOUR_STEPS: PageTourStep[] = [
  {
    element: '[data-tour="mktg-header"]',
    popover: {
      title: "📣 Marketing Groups",
      description:
        "Kelola grup target marketing. Setiap grup berisi daftar kontak untuk kampanye outreach.",
    },
  },
  {
    element: '[data-tour="mktg-type-filter"]',
    popover: {
      title: "🏷️ Filter Tipe",
      description:
        "Filter grup berdasarkan tipe: CORPORATE, GOVERNMENT, UNIVERSITY, atau semua.",
    },
  },
  {
    element: '[data-tour="mktg-group-list"]',
    popover: {
      title: "📋 Daftar Grup",
      description:
        "Setiap kartu adalah satu grup target. Klik untuk lihat anggota, kirim blast, atau edit grup.",
    },
  },
];
