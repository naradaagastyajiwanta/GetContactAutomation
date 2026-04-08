import {
  Instagram,
  Smartphone,
  Sliders,
  Activity,
  ArrowRight,
} from "lucide-react";
import { Link } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import type { AuthUser } from "../../../lib/types";

interface Props {
  user: AuthUser;
  onNavigateAway: () => void;
}

interface ChecklistItem {
  id: string;
  icon: LucideIcon;
  title: string;
  description: string;
  to: string;
  linkLabel: string;
}

const CHECKLIST_ITEMS: ChecklistItem[] = [
  {
    id: "instagram",
    icon: Instagram,
    title: "Hubungkan Akun Instagram",
    description: "Diperlukan untuk scraping postingan dan handle kampus",
    to: "/settings",
    linkLabel: "Buka Settings",
  },
  {
    id: "whatsapp",
    icon: Smartphone,
    title: "Hubungkan Perangkat WhatsApp",
    description: "Diperlukan untuk mengirim pesan outreach otomatis",
    to: "/whatsapp",
    linkLabel: "Buka WhatsApp",
  },
  {
    id: "api",
    icon: Sliders,
    title: "Konfigurasi API Keys",
    description: "Serper, Apify, ScrapingBot untuk menjalankan pipeline",
    to: "/settings",
    linkLabel: "Buka Config",
  },
  {
    id: "health",
    icon: Activity,
    title: "Cek System Health",
    description: "Pastikan semua service berjalan normal sebelum mulai",
    to: "/settings",
    linkLabel: "Cek Health",
  },
];

export function OnboardingStep4SetupChecklist({ onNavigateAway }: Props) {
  return (
    <div>
      <div className="mb-4 text-center">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          Setup Awal
        </h3>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Selesaikan langkah-langkah ini sebelum menjalankan pipeline pertama
        </p>
      </div>

      <div className="flex flex-col gap-3">
        {CHECKLIST_ITEMS.map(
          ({ id, icon: Icon, title, description, to, linkLabel }) => (
            <div
              key={id}
              className="flex flex-wrap items-center gap-3 rounded-xl border border-gray-200 bg-gray-50 p-3 sm:gap-4 sm:p-4 dark:border-gray-700 dark:bg-gray-900/40"
            >
              <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-indigo-100 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400">
                <Icon className="h-5 w-5" />
              </div>

              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  {title}
                </p>
                <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                  {description}
                </p>
              </div>

              <Link
                to={to}
                onClick={onNavigateAway}
                className="ml-auto flex flex-shrink-0 items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300"
              >
                {linkLabel}
                <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
          ),
        )}
      </div>
    </div>
  );
}
