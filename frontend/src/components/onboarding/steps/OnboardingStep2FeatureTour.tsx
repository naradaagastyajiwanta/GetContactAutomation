import {
  GitBranch,
  Megaphone,
  Search,
  UserSearch,
  Video,
  Mail,
} from "lucide-react";
import { Card } from "../../ui/Card";
import type { AuthUser } from "../../../lib/types";

interface Props {
  user: AuthUser;
  onNavigateAway: () => void;
}

const FEATURES = [
  {
    icon: GitBranch,
    name: "Pipeline",
    description: "PDDIKTI → Instagram → WhatsApp outreach otomatis",
    color: "bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400",
  },
  {
    icon: Megaphone,
    name: "WA Blast",
    description: "Kirim pesan massal WhatsApp ke ribuan kontak",
    color:
      "bg-green-50 text-green-600 dark:bg-green-900/20 dark:text-green-400",
  },
  {
    icon: Search,
    name: "Marketing",
    description: "Otomatisasi multi-agent untuk prospek korporat",
    color:
      "bg-purple-50 text-purple-600 dark:bg-purple-900/20 dark:text-purple-400",
  },
  {
    icon: UserSearch,
    name: "CRM & Profiling",
    description: "Profil kontak lengkap & knowledge graph PIC",
    color:
      "bg-orange-50 text-orange-600 dark:bg-orange-900/20 dark:text-orange-400",
  },
  {
    icon: Video,
    name: "Audiensi",
    description: "Jadwalkan rapat formal dengan surat PDF otomatis",
    color: "bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400",
  },
  {
    icon: Mail,
    name: "Email Blast",
    description: "Kirim email massal via SMTP dengan rotasi proxy",
    color: "bg-teal-50 text-teal-600 dark:bg-teal-900/20 dark:text-teal-400",
  },
];

export function OnboardingStep2FeatureTour(_props: Props) {
  return (
    <div>
      <div className="mb-4 text-center">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          Fitur Utama
        </h3>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Semua yang kamu butuhkan untuk outreach di satu tempat
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {FEATURES.map(({ icon: Icon, name, description, color }) => (
          <Card key={name} padding={false} className="p-4">
            <div className="flex items-start gap-3">
              <div
                className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg ${color}`}
              >
                <Icon className="h-4 w-4" />
              </div>
              <div>
                <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                  {name}
                </p>
                <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                  {description}
                </p>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
