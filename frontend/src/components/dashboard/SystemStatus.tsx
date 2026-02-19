import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card'
import { useControlStatus } from '../../hooks/useControl'
import { useHealth } from '../../hooks/useHealth'

export function SystemStatus() {
  const { data: control } = useControlStatus()
  const { data: health } = useHealth()

  const waConnected = health?.whatsapp?.connected ?? false
  const paused = control?.paused ?? false

  return (
    <Card>
      <CardHeader>
        <CardTitle>System Status</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-600 dark:text-gray-400">
              WhatsApp
            </span>
            <div className="flex items-center gap-2">
              <span
                className={`h-2.5 w-2.5 rounded-full ${
                  waConnected ? 'bg-green-500' : 'bg-red-500'
                }`}
              />
              <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {waConnected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-600 dark:text-gray-400">
              Bot Status
            </span>
            <div className="flex items-center gap-2">
              <span
                className={`h-2.5 w-2.5 rounded-full ${
                  paused ? 'bg-yellow-500' : 'bg-green-500'
                }`}
              />
              <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {paused ? 'Paused' : 'Running'}
              </span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
