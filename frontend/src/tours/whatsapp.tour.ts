import type { PageTourStep } from "../hooks/usePageTour";

export const WHATSAPP_TOUR_STEPS: PageTourStep[] = [
  {
    element: '[data-tour="whatsapp-status"]',
    popover: {
      title: "📱 Status Perangkat",
      description:
        "Lihat berapa perangkat WA terhubung dan jumlah pesan dalam antrian pengiriman saat ini. Pastikan minimal 1 device online sebelum menjalankan pipeline.",
      side: "bottom",
      align: "start",
    },
  },
  {
    element: '[data-tour="whatsapp-tabs"]',
    popover: {
      title: "🗂️ 3 Tab",
      description:
        "<b>Devices</b> — kelola & scan QR perangkat WA.<br><b>Quick Test</b> — kirim test pesan ke nomor tertentu.<br><b>Blast WA</b> — panel pengiriman massal langsung.",
      side: "bottom",
      align: "start",
    },
  },
  {
    element: '[data-tour="whatsapp-devices"]',
    popover: {
      title: "📲 Perangkat Kamu",
      description:
        "Status koneksi perangkat aktif. Scan QR code untuk menghubungkan nomor WhatsApp baru ke sistem.",
      side: "top",
      align: "start",
    },
  },
];
