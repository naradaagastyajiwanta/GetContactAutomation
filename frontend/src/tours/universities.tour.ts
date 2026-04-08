import type { PageTourStep } from "../hooks/usePageTour";

export const UNIVERSITIES_TOUR_STEPS: PageTourStep[] = [
  {
    element: '[data-tour="universities-actions"]',
    popover: {
      title: "➕ Actions",
      description:
        "Tambah universitas manual, import bulk dari CSV/Excel, atau export seluruh data kontak. Tombol Bulk Select untuk aksi massal ke banyak universitas sekaligus.",
      side: "bottom",
      align: "end",
    },
  },
  {
    element: '[data-tour="universities-filters"]',
    popover: {
      title: "🔍 Filter & Search",
      description:
        "Cari universitas berdasarkan nama, filter by status IG, provinsi, atau grup. Filter aktif ditampilkan sebagai chip — klik X untuk hapus satu per satu.",
      side: "bottom",
      align: "start",
    },
  },
  {
    element: '[data-tour="universities-table"]',
    popover: {
      title: "🏛️ Tabel Universitas",
      description:
        "Klik baris untuk lihat detail lengkap: scraping history, status pipeline, dan kontak yang ditemukan. Centang checkbox untuk aksi bulk.",
      side: "top",
      align: "start",
    },
  },
];
