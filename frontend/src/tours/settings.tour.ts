import type { PageTourStep } from "../hooks/usePageTour";

export const SETTINGS_TOUR_STEPS: PageTourStep[] = [
  {
    element: '[data-tour="settings-nav"]',
    popover: {
      title: "⚙️ Navigasi Settings",
      description:
        "Empat tab utama: Control (status bot & health), Instagram (akun IG & ScrapingBot), Config (API keys, model AI, semua pengaturan), dan Access (role & audit log).",
    },
    permission: "settings.manage",
  },
  {
    element: '[data-tour="settings-control"]',
    popover: {
      title: "🎛️ Control & Health",
      description:
        "Pause/resume bot, aktifkan fitur (chatbot, audiensi, multi-agent research), dan pantau status koneksi API, WhatsApp, serta sesi Instagram.",
    },
    permission: "settings.manage",
  },
  {
    element: '[data-tour="settings-config"]',
    popover: {
      title: "🔑 Config & Export",
      description:
        "Kelola semua pengaturan sistem: API keys (OpenAI, Serper, Apify), rate limits, AI model, DMS integration, dan behavior agen. Export data juga tersedia di sini.",
    },
    permission: "settings.manage",
  },
];
