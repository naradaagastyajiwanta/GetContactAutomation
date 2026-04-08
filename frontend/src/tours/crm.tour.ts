import type { PageTourStep } from "../hooks/usePageTour";

export const CRM_TOUR_STEPS: PageTourStep[] = [
  {
    element: '[data-tour="crm-new-btn"]',
    popover: {
      title: "➕ Buat Profil Baru",
      description:
        "Pilih PIC dari DMS atau input manual. Sistem AI akan riset profil lengkap: jabatan, latar belakang akademik, kanal komunikasi, dan minat personal.",
      side: "bottom",
      align: "end",
    },
    permission: "crm.manage",
  },
  {
    element: '[data-tour="crm-stats"]',
    popover: {
      title: "📊 Statistik Profiling",
      description:
        "Total request, berapa yang selesai diproses, sedang berjalan, dan rata-rata confidence score AI dalam membangun profil.",
      side: "bottom",
      align: "start",
    },
  },
  {
    element: '[data-tour="crm-status-filter"]',
    popover: {
      title: "🔽 Filter by Status",
      description:
        "Lihat profil berdasarkan tahap: Pending (antri), Processing (sedang diproses AI), Completed (selesai), atau Failed (gagal).",
      side: "bottom",
      align: "start",
    },
  },
];
