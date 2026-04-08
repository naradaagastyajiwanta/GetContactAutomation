import type { PageTourStep } from "../hooks/usePageTour";

export const EMAIL_BLAST_TOUR_STEPS: PageTourStep[] = [
  {
    element: '[data-tour="email-left-rail"]',
    popover: {
      title: "📬 Navigation Email",
      description:
        "Navigasi folder: Inbox, Sent, Draft, dan filter per tag. Klik folder untuk melihat email terkait.",
    },
  },
  {
    element: '[data-tour="email-content"]',
    popover: {
      title: "✉️ Area Email",
      description:
        "Baca email masuk, compose email baru, atau lihat thread lengkap di sini.",
    },
  },
];
