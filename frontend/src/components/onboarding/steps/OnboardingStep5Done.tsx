import {
  CheckCircle2,
  LayoutDashboard,
  GitBranch,
  Megaphone,
  Map,
} from "lucide-react";
import { Link } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import type { AuthUser } from "../../../lib/types";
import { Button } from "../../ui/Button";

interface Props {
  user: AuthUser;
  onNavigateAway: () => void;
  onStartTour: () => void;
}

interface QuickLink {
  icon: LucideIcon;
  label: string;
  to: string;
  description: string;
}

const QUICK_LINKS: QuickLink[] = [
  {
    icon: LayoutDashboard,
    label: "Dashboard",
    to: "/",
    description: "Pantau statistik real-time",
  },
  {
    icon: GitBranch,
    label: "Pipeline",
    to: "/pipeline",
    description: "Jalankan agent pertama",
  },
  {
    icon: Megaphone,
    label: "WA Blast",
    to: "/blast",
    description: "Buat kampanye blast",
  },
];

export function OnboardingStep5Done({
  user,
  onNavigateAway,
  onStartTour,
}: Props) {
  return (
    <div className="flex flex-col items-center py-4 text-center">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400">
        <CheckCircle2 className="h-9 w-9" />
      </div>

      <h3 className="text-xl font-semibold text-gray-900 dark:text-white">
        Semua siap, {user.name.split(" ")[0]}!
      </h3>
      <p className="mt-2 max-w-sm text-sm text-gray-500 dark:text-gray-400">
        Kamu sudah mengenal platform ini. Mulai dari mana saja — atau kembali
        kapanpun kamu perlu.
      </p>

      <div className="mt-6 grid w-full grid-cols-1 gap-3 min-[400px]:grid-cols-3">
        {QUICK_LINKS.map(({ icon: Icon, label, to, description }) => (
          <Link
            key={to}
            to={to}
            onClick={onNavigateAway}
            className="group flex flex-col items-center gap-2 rounded-xl border border-gray-200 bg-gray-50 p-4 transition-colors hover:border-indigo-300 hover:bg-indigo-50 dark:border-gray-700 dark:bg-gray-900/40 dark:hover:border-indigo-700 dark:hover:bg-indigo-900/20"
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white text-indigo-600 shadow-sm group-hover:bg-indigo-600 group-hover:text-white dark:bg-gray-800 dark:text-indigo-400 dark:group-hover:bg-indigo-600 dark:group-hover:text-white">
              <Icon className="h-4 w-4" />
            </div>
            <div>
              <p className="text-xs font-semibold text-gray-900 dark:text-white">
                {label}
              </p>
              <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500">
                {description}
              </p>
            </div>
          </Link>
        ))}
      </div>

      <div className="mt-6 flex w-full flex-col items-stretch gap-2 sm:w-auto sm:flex-row sm:items-center sm:gap-3">
        <Button variant="primary" size="md" onClick={onStartTour}>
          <Map className="h-4 w-4" />
          Mulai Tour Aplikasi
        </Button>
        <Button variant="ghost" size="md" onClick={onNavigateAway}>
          Lewati
        </Button>
      </div>

      <p className="mt-3 text-xs text-gray-400 dark:text-gray-500">
        Tour akan menunjukkan letak setiap menu secara langsung
      </p>
    </div>
  );
}
