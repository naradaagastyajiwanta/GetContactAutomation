import { useState } from "react";
import {
  Settings,
  Instagram,
  Sliders,
  ShieldCheck,
  Cookie,
  Bot,
  Zap,
} from "lucide-react";
import { cn } from "../lib/utils";
import { useAuth } from "../context/AuthContext";
import { usePageTour } from "../hooks/usePageTour";
import { SETTINGS_TOUR_STEPS } from "../tours/settings.tour";
import { ControlPanel } from "../components/settings/ControlPanel";
import { HealthStatus } from "../components/settings/HealthStatus";
import { ConfigDisplay } from "../components/settings/ConfigDisplay";
import { ExportSection } from "../components/settings/ExportSection";
import { IGAccountsManager } from "../components/settings/IGAccountsManager";
import { IGSessionUploader } from "../components/settings/IGSessionUploader";
import { ScrapingBotAccountsManager } from "../components/settings/ScrapingBotAccountsManager";
import { AuthAccessManager } from "../components/settings/AuthAccessManager";
import { AuthAuditLogViewer } from "../components/settings/AuthAuditLogViewer";

type TabId = "control" | "instagram" | "config" | "access";
type IgTabId = "accounts" | "sessions" | "scrapingbot";

function TabButton({
  icon: Icon,
  label,
  isActive,
  onClick,
  dataTour,
}: {
  icon: React.ElementType;
  label: string;
  isActive: boolean;
  onClick: () => void;
  dataTour?: string;
}) {
  return (
    <button
      data-tour={dataTour}
      onClick={onClick}
      className={cn(
        "flex items-center gap-2 px-5 py-2.5 text-sm font-medium transition-all rounded-t-lg border-b-2",
        isActive
          ? "text-indigo-600 dark:text-indigo-400 border-indigo-600 dark:border-indigo-400 bg-white dark:bg-gray-800"
          : "text-gray-500 dark:text-gray-400 border-transparent hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600",
      )}
    >
      <Icon className="w-4 h-4" />
      {label}
    </button>
  );
}

export default function SettingsPage() {
  const { hasPermission } = useAuth();
  const isAdmin = hasPermission("*");
  const canManageSettings = hasPermission("settings.manage"); // admin only

  // Operators default to instagram (the only tab they can see)
  const [activeTab, setActiveTab] = useState<TabId>(
    canManageSettings ? "control" : "instagram",
  );
  const [igTab, setIgTab] = useState<IgTabId>("accounts");

  usePageTour("settings", SETTINGS_TOUR_STEPS);

  const igSubTabs: { id: IgTabId; icon: React.ElementType; label: string }[] = [
    { id: "accounts", icon: Instagram, label: "IG Accounts" },
    { id: "sessions", icon: Cookie, label: "Sessions" },
    { id: "scrapingbot", icon: Bot, label: "ScrapingBot" },
  ];

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 space-y-6">
      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        <div className="p-2.5 bg-gradient-to-br from-gray-600 to-gray-800 dark:from-gray-500 dark:to-gray-700 rounded-xl shadow-md">
          <Settings className="w-6 h-6 text-white" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            Settings
          </h1>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            System configuration and access management
          </p>
        </div>
      </div>

      {/* ── Primary tab bar ──────────────────────────────────────────────── */}
      <div
        data-tour="settings-nav"
        className="flex gap-1 border-b border-gray-200 dark:border-gray-700"
      >
        {canManageSettings && (
          <TabButton
            icon={Settings}
            label="Control"
            isActive={activeTab === "control"}
            onClick={() => setActiveTab("control")}
            dataTour="settings-control"
          />
        )}
        <TabButton
          icon={Instagram}
          label="Instagram"
          isActive={activeTab === "instagram"}
          onClick={() => setActiveTab("instagram")}
        />
        {canManageSettings && (
          <TabButton
            icon={Sliders}
            label="Config"
            isActive={activeTab === "config"}
            onClick={() => setActiveTab("config")}
            dataTour="settings-config"
          />
        )}
        {isAdmin && (
          <TabButton
            icon={ShieldCheck}
            label="Access"
            isActive={activeTab === "access"}
            onClick={() => setActiveTab("access")}
          />
        )}
      </div>

      {/* ── Tab content panel ────────────────────────────────────────────── */}
      <div className="bg-white dark:bg-gray-800 rounded-b-xl rounded-tr-xl shadow-sm border border-t-0 border-gray-200 dark:border-gray-700">
        {/* Control tab */}
        {activeTab === "control" && (
          <div className="p-6">
            <div className="grid gap-6 lg:grid-cols-2">
              <ControlPanel />
              <HealthStatus />
            </div>
          </div>
        )}

        {/* Instagram tab */}
        {activeTab === "instagram" && (
          <div className="p-6 space-y-6">
            {/* Info banner */}
            <div className="rounded-xl border border-indigo-200 bg-gradient-to-r from-indigo-50 to-purple-50 dark:from-indigo-900/20 dark:to-purple-900/20 dark:border-indigo-700/50 p-4">
              <div className="flex items-start gap-3">
                <div className="p-1.5 rounded-lg bg-indigo-100 dark:bg-indigo-800/50 flex-shrink-0">
                  <Zap className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
                </div>
                <div className="space-y-2">
                  <p className="text-sm font-semibold text-indigo-900 dark:text-indigo-200">
                    Tambahkan sebanyak mungkin akun untuk performa maksimal
                  </p>
                  <div className="grid gap-1.5 sm:grid-cols-3">
                    <div className="flex items-start gap-2 rounded-lg bg-white/60 dark:bg-gray-800/40 px-3 py-2">
                      <Instagram className="h-3.5 w-3.5 text-pink-500 mt-0.5 flex-shrink-0" />
                      <div>
                        <p className="text-xs font-medium text-gray-800 dark:text-gray-200">
                          IG Accounts
                        </p>
                        <p className="text-[11px] text-gray-500 dark:text-gray-400 leading-snug">
                          Makin banyak akun, makin cepat scraping following list
                          & data akun private
                        </p>
                      </div>
                    </div>
                    <div className="flex items-start gap-2 rounded-lg bg-white/60 dark:bg-gray-800/40 px-3 py-2">
                      <Cookie className="h-3.5 w-3.5 text-amber-500 mt-0.5 flex-shrink-0" />
                      <div>
                        <p className="text-xs font-medium text-gray-800 dark:text-gray-200">
                          Sessions
                        </p>
                        <p className="text-[11px] text-gray-500 dark:text-gray-400 leading-snug">
                          Rotasi otomatis saat satu sesi kena rate-limit —
                          minimal 3 sesi untuk optimal
                        </p>
                      </div>
                    </div>
                    <div className="flex items-start gap-2 rounded-lg bg-white/60 dark:bg-gray-800/40 px-3 py-2">
                      <Bot className="h-3.5 w-3.5 text-blue-500 mt-0.5 flex-shrink-0" />
                      <div>
                        <p className="text-xs font-medium text-gray-800 dark:text-gray-200">
                          ScrapingBot
                        </p>
                        <p className="text-[11px] text-gray-500 dark:text-gray-400 leading-snug">
                          Free tier 500 kredit/bulan — daftar banyak akun pakai
                          temp email untuk kuota besar
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Instagram sub-tab bar — pill style */}
            <div className="flex gap-1 rounded-xl bg-gray-100/80 dark:bg-gray-700/60 p-1 w-fit">
              {igSubTabs.map(({ id, icon: Icon, label }) => (
                <button
                  key={id}
                  onClick={() => setIgTab(id)}
                  className={cn(
                    "flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition-all",
                    igTab === id
                      ? "bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 shadow-sm"
                      : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </button>
              ))}
            </div>

            {/* Instagram sub-tab content */}
            {igTab === "accounts" && <IGAccountsManager />}
            {igTab === "sessions" && <IGSessionUploader />}
            {igTab === "scrapingbot" && <ScrapingBotAccountsManager />}
          </div>
        )}

        {/* Config tab */}
        {activeTab === "config" && (
          <div className="p-6 space-y-6">
            <ConfigDisplay />
            <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
              <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3">
                Data Export
              </p>
              <ExportSection />
            </div>
          </div>
        )}

        {/* Access tab — admin only */}
        {activeTab === "access" && isAdmin && (
          <div className="p-6 space-y-6">
            <AuthAccessManager />
            <AuthAuditLogViewer />
          </div>
        )}
      </div>
    </div>
  );
}
