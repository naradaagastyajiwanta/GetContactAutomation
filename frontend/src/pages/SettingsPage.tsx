import { Settings, Activity, Instagram, Sliders, Download, Shield } from 'lucide-react'
import { SectionNav, type SectionItem } from '../components/settings/SectionNav'
import { ControlPanel } from '../components/settings/ControlPanel'
import { HealthStatus } from '../components/settings/HealthStatus'
import { ConfigDisplay } from '../components/settings/ConfigDisplay'
import { ExportSection } from '../components/settings/ExportSection'
import { IGSessionUploader } from '../components/settings/IGSessionUploader'
import { IGAccountsManager } from '../components/settings/IGAccountsManager'
import { AuthAccessManager } from '../components/settings/AuthAccessManager'
import { AuthAuditLogViewer } from '../components/settings/AuthAuditLogViewer'

const SECTIONS: SectionItem[] = [
  { id: 'control', label: 'Control', icon: <Settings className="h-4 w-4" /> },
  { id: 'health', label: 'Health', icon: <Activity className="h-4 w-4" /> },
  { id: 'instagram', label: 'Instagram', icon: <Instagram className="h-4 w-4" /> },
  { id: 'access', label: 'Access', icon: <Shield className="h-4 w-4" /> },
  { id: 'config', label: 'Config', icon: <Sliders className="h-4 w-4" /> },
  { id: 'export', label: 'Export', icon: <Download className="h-4 w-4" /> },
]

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Settings</h1>

      <SectionNav sections={SECTIONS} />

      <section id="settings-control">
        <div className="grid gap-6 lg:grid-cols-2">
          <ControlPanel />
          <HealthStatus />
        </div>
      </section>

      <section id="settings-health" />

      <section id="settings-instagram" className="space-y-4">
        <IGAccountsManager />
        <IGSessionUploader />
      </section>

      <section id="settings-access">
        <div className="space-y-4">
          <AuthAccessManager />
          <AuthAuditLogViewer />
        </div>
      </section>

      <section id="settings-config">
        <ConfigDisplay />
      </section>

      <section id="settings-export">
        <ExportSection />
      </section>
    </div>
  )
}
