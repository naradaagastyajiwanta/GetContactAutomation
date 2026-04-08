import { Mail } from "lucide-react";
import { Badge } from "../../ui/Badge";
import type { AuthUser } from "../../../lib/types";

interface Props {
  user: AuthUser;
  onNavigateAway: () => void;
}

const ROLE_LABELS: Record<string, { label: string; className: string }> = {
  admin: {
    label: "Admin",
    className: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  },
  operator: {
    label: "Operator",
    className:
      "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  },
  viewer: {
    label: "Viewer",
    className: "bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300",
  },
};

export function OnboardingStep3Profile({ user }: Props) {
  const initial = user.name.charAt(0).toUpperCase();
  const hasFullAccess = user.permissions.includes("*");
  const permissionSummary = hasFullAccess
    ? "Akses Penuh"
    : `${user.permissions.length} permission aktif`;

  return (
    <div className="flex flex-col items-center py-4">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-indigo-600 text-2xl font-bold text-white shadow-md">
        {initial}
      </div>

      <h3 className="text-xl font-semibold text-gray-900 dark:text-white">
        {user.name}
      </h3>

      <div className="mt-1 flex items-center gap-1.5 text-sm text-gray-500 dark:text-gray-400">
        <Mail className="h-3.5 w-3.5" />
        <span>{user.email}</span>
      </div>

      <div className="mt-4 flex flex-wrap justify-center gap-2">
        {user.roles.map((role) => {
          const config = ROLE_LABELS[role];
          return (
            <Badge key={role} variant={config?.className}>
              {config?.label ?? role}
            </Badge>
          );
        })}
      </div>

      <div className="mt-6 w-full max-w-xs rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-900/40">
        <div className="flex items-center justify-between text-sm">
          <span className="text-gray-500 dark:text-gray-400">Level Akses</span>
          <span className="font-medium text-gray-900 dark:text-white">
            {permissionSummary}
          </span>
        </div>
        <div className="mt-2 flex items-center justify-between text-sm">
          <span className="text-gray-500 dark:text-gray-400">DMS Level</span>
          <span className="font-medium text-gray-900 dark:text-white">
            {user.dms_user_level || "—"}
          </span>
        </div>
      </div>
    </div>
  );
}
