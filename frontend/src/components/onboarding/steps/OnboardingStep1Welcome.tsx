import { Sparkles } from "lucide-react";
import type { AuthUser } from "../../../lib/types";

interface Props {
  user: AuthUser;
  onNavigateAway: () => void;
}

export function OnboardingStep1Welcome({ user }: Props) {
  return (
    <div className="flex flex-col items-center justify-center py-4 text-center sm:py-8">
      <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-600 text-white shadow-lg">
        <Sparkles className="h-8 w-8" />
      </div>

      <h2 className="mb-2 text-2xl font-bold text-gray-900 dark:text-white sm:text-3xl">
        Halo, {user.name}!
      </h2>

      <span className="mb-4 inline-block rounded-full bg-indigo-100 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300">
        DMS Marketing
      </span>

      <p className="max-w-md text-base text-gray-500 dark:text-gray-400">
        Platform outreach otomatis untuk menjangkau kampus dan korporat di
        seluruh Indonesia — dari scraping data hingga percakapan AI dan kampanye
        blast.
      </p>

      <p className="mt-6 text-sm text-gray-400 dark:text-gray-500">
        Ikuti panduan singkat ini untuk memulai.
      </p>
    </div>
  );
}
