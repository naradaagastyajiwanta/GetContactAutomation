import type { PageTourStep } from "../hooks/usePageTour";

export const UNIVERSITY_GROUPS_TOUR_STEPS: PageTourStep[] = [
  {
    element: '[data-tour="uni-groups-left"]',
    popover: {
      title: "📂 Daftar Grup",
      description:
        "Semua grup universitas yang sudah dibuat. Klik grup untuk melihat anggotanya di panel kanan.",
    },
  },
  {
    element: '[data-tour="uni-groups-new-btn"]',
    popover: {
      title: "➕ Buat Grup Baru",
      description:
        "Buat grup baru untuk mengorganisir universitas berdasarkan region, prioritas, atau kampanye tertentu.",
    },
  },
  {
    element: '[data-tour="uni-groups-detail"]',
    popover: {
      title: "📋 Detail Grup",
      description:
        "Lihat universitas dalam grup ini, tambah/hapus anggota, atau jalankan aksi massal.",
    },
  },
];
