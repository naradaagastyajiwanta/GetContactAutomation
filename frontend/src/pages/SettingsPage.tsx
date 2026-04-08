import { Settings, Activity, Instagram, Sliders, Download } from "lucide-react";
import { usePageTour } from "../hooks/usePageTour";
import { SETTINGS_TOUR_STEPS } from "../tours/settings.tour";
import {
  SectionNav,
  type SectionItem,
} from "../components/settings/SectionNav";
import { ControlPanel } from "../components/settings/ControlPanel";
import { HealthStatus } from "../components/settings/HealthStatus";
import { ConfigDisplay } from "../components/settings/ConfigDisplay";
import { ExportSection } from "../components/settings/ExportSection";
import { IGAccountsManager } from "../components/settings/IGAccountsManager";

const SECTIONS: SectionItem[] = [
  { id: "control", label: "Control", icon: <Settings className="h-4 w-4" /> },
  { id: "health", label: "Health", icon: <Activity className="h-4 w-4" /> },
  {
    id: "instagram",
    label: "Instagram",
    icon: <Instagram className="h-4 w-4" />,
  },
  { id: "config", label: "Config", icon: <Sliders className="h-4 w-4" /> },
  { id: "export", label: "Export", icon: <Download className="h-4 w-4" /> },
];

export default function SettingsPage() {
  usePageTour("settings", SETTINGS_TOUR_STEPS);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
        Settings
      </h1>

      <div data-tour="settings-nav">
        <SectionNav sections={SECTIONS} />
      </div>

      <section id="settings-control" data-tour="settings-control">
        <div className="grid gap-6 lg:grid-cols-2">
          <ControlPanel />
          <HealthStatus />
        </div>
      </section>

      <section id="settings-health" />

      <section id="settings-instagram">
        <IGAccountsManager />
      </section>

      <section id="settings-config" data-tour="settings-config">
        <ConfigDisplay />
      </section>

      <section id="settings-export">
        <ExportSection />
      </section>
    </div>
  );
}
