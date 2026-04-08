import { driver } from "driver.js";

export function useTour(hasPermission: (permission?: string) => boolean) {
  const startTour = () => {
    requestAnimationFrame(() => {
      const baseSteps = [
        {
          popover: {
            title: "👋 Kenali Aplikasinya",
            description:
              "Kami akan menunjukkan di mana letak setiap menu dan fitur. Ikuti langkah-langkah berikut untuk menjelajahi aplikasi!",
          },
        },
        {
          element: '[data-tour="sidebar"]',
          popover: {
            title: "🗂️ Navigasi Utama",
            description:
              "Sidebar kiri adalah pusat navigasi aplikasi. Semua fitur dapat diakses dari menu-menu di sini.",
            side: "right",
            align: "center",
          },
        },
        {
          element: '[data-tour="section-overview"]',
          popover: {
            title: "📊 Overview",
            description:
              "<b>Dashboard</b> — pantau statistik real-time pipeline dan kuota harian.<br><br><b>Pipeline</b> — jalankan agen scraping dari PDDIKTI → Instagram → nomor HP.",
            side: "right",
            align: "start",
          },
        },
        {
          element: '[data-tour="section-data-list"]',
          popover: {
            title: "🗄️ Data List",
            description:
              "<b>Universities</b> — database universitas hasil scraping PDDIKTI.<br><br><b>Corporate</b> — database korporat & perusahaan untuk target marketing.",
            side: "right",
            align: "start",
          },
        },
        {
          element: '[data-tour="section-outreach"]',
          popover: {
            title: "💬 Outreach",
            description:
              "<b>Conversations</b> — riwayat percakapan WhatsApp dengan kontak.<br><br><b>Audiensi</b> — kelola antrian dan jadwal pertemuan formal.<br><br><b>Audiensi Schedules</b> — sinkronisasi jadwal dari DMS.",
            side: "right",
            align: "start",
          },
        },
        {
          element: '[data-tour="section-broadcast"]',
          popover: {
            title: "📢 Broadcast",
            description:
              "<b>WhatsApp</b> — manajemen perangkat WA & QR scan.<br><br><b>WA Blast</b> — kirim pesan massal WhatsApp ke ribuan kontak.<br><br><b>Email Blast</b> — kampanye email massal via SMTP.",
            side: "right",
            align: "start",
          },
        },
        {
          element: '[data-tour="section-ai-data"]',
          popover: {
            title: "🤖 AI & Data",
            description:
              "<b>Learning</b> — training & manajemen pelajaran agen AI.<br><br><b>Knowledge Base</b> — dokumen rujukan untuk agen.<br><br><b>PIC Profiling</b> — profil lengkap kontak & knowledge graph korporat.",
            side: "right",
            align: "start",
          },
        },
      ];

      // Admin-only steps — only shown if user has settings.manage permission
      const adminSteps = hasPermission("settings.manage")
        ? [
            {
              element: '[data-tour="nav-settings"]',
              popover: {
                title: "⚙️ Settings",
                description:
                  "Konfigurasi seluruh sistem di sini: tambah akun Instagram, hubungkan perangkat WhatsApp, atur API keys (Serper, Apify), dan pantau health seluruh service.",
                side: "right",
                align: "end",
              },
            },
          ]
        : [];

      const d = driver({
        animate: true,
        overlayOpacity: 0.65,
        showProgress: true,
        progressText: "{{current}} dari {{total}}",
        nextBtnText: "Lanjut →",
        prevBtnText: "← Kembali",
        doneBtnText: "Selesai ✓",
        allowClose: true,
        steps: [...baseSteps, ...adminSteps],
      });

      d.drive();
    });
  };

  return { startTour };
}
