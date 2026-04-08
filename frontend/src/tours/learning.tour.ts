import type { PageTourStep } from "../hooks/usePageTour";

export const LEARNING_TOUR_STEPS: PageTourStep[] = [
  {
    element: '[data-tour="learning-stats"]',
    popover: {
      title: "📈 Statistik Learning",
      description:
        "Total lessons aktif yang digunakan agen, analisis percakapan yang belum diproses, dan distribusi lessons per situasi (initial contact, follow-up, objection handling, dll).",
      side: "bottom",
      align: "start",
    },
  },
  {
    element: '[data-tour="learning-lessons"]',
    popover: {
      title: "🧠 Learned Lessons",
      description:
        "Pelajaran yang sudah dipelajari AI dari ribuan percakapan nyata. Setiap lesson punya confidence score dan strategi yang direkomendasikan untuk situasi tertentu.",
      side: "top",
      align: "start",
    },
  },
  {
    element: '[data-tour="learning-analyses"]',
    popover: {
      title: "🔬 Recent Analyses",
      description:
        "Analisis terbaru dari percakapan yang sudah selesai. Ini adalah bahan mentah yang digunakan agen AI untuk terus belajar dan meningkatkan performa.",
      side: "top",
      align: "start",
    },
  },
];
