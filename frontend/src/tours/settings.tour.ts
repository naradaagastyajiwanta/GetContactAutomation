import type { PageTourStep } from "../hooks/usePageTour";

export const SETTINGS_TOUR_STEPS: PageTourStep[] = [
  {
    element: '[data-tour="settings-nav"]',
    popover: {
      title: "⚙️ Navigasi Settings",
      description:
        "Navigasi ke section yang berbeda: IG Config, WhatsApp, API Keys, System Health, dan konfigurasi lainnya.",
    },
    permission: "settings.manage",
  },
  {
    element: '[data-tour="settings-control"]',
    popover: {
      title: "🎛️ Konfigurasi Utama",
      description:
        "Atur parameter sistem: rate limits, AI model, DMS integration, dan behavior agen.",
    },
    permission: "settings.manage",
  },
  {
    element: '[data-tour="settings-config"]',
    popover: {
      title: "🔑 API & Integrasi",
      description:
        "Kelola API keys untuk OpenAI, Serper, Apify, dan integrasi eksternal lainnya.",
    },
    permission: "settings.manage",
  },
];
