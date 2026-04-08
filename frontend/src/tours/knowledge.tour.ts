import type { PageTourStep } from "../hooks/usePageTour";

export const KNOWLEDGE_TOUR_STEPS: PageTourStep[] = [
  {
    element: '[data-tour="kb-tabs"]',
    popover: {
      title: "🗂️ Dua Mode",
      description:
        "<b>Contact Finder</b> — knowledge untuk agen WhatsApp outreach kampus.<br><b>Audiensi</b> — knowledge untuk agen penjadwalan meeting formal.",
      side: "bottom",
      align: "start",
    },
  },
  {
    element: '[data-tour="kb-instructions"]',
    popover: {
      title: "📝 Custom Instructions",
      description:
        "Instruksi khusus yang selalu diberikan ke agen AI sebelum memulai percakapan. Atur tone, gaya bicara, atau aturan tertentu yang harus diikuti agen.",
      side: "bottom",
      align: "start",
    },
    permission: "knowledge.manage",
  },
  {
    element: '[data-tour="kb-items"]',
    popover: {
      title: "📚 Knowledge Items",
      description:
        "Dokumen, FAQ, atau informasi tambahan yang bisa direferensikan agen saat percakapan. Upload file (PDF, DOCX, TXT) atau tambah item manual.",
      side: "top",
      align: "start",
    },
  },
];
