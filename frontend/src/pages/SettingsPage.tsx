import { ControlPanel } from '../components/settings/ControlPanel'
import { HealthStatus } from '../components/settings/HealthStatus'
import { ConfigDisplay } from '../components/settings/ConfigDisplay'
import { ExportSection } from '../components/settings/ExportSection'

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Settings</h1>

      <div className="grid gap-6 lg:grid-cols-2">
        <ControlPanel />
        <HealthStatus />
      </div>

      <ConfigDisplay />

      <ExportSection />
    </div>
  )
}
