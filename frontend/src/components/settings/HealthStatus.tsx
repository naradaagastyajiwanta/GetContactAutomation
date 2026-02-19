import { Activity } from 'lucide-react'
import { useHealth } from '../../hooks/useHealth'
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card'
import { Spinner } from '../ui/Spinner'
import { cn } from '../../lib/utils'

export function HealthStatus() {
  const { data: health, isLoading } = useHealth()

  const waConnected = health?.whatsapp?.connected ?? false

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-gray-500 dark:text-gray-400" />
          <CardTitle>System Health</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex justify-center py-4">
            <Spinner size="md" />
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-500 dark:text-gray-400">API Status</span>
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    'h-2.5 w-2.5 rounded-full',
                    health?.status === 'ok'
                      ? 'bg-green-400 dark:bg-green-500'
                      : 'bg-red-400 dark:bg-red-500',
                  )}
                />
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {health?.status === 'ok' ? 'Healthy' : 'Error'}
                </span>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-500 dark:text-gray-400">WhatsApp</span>
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    'h-2.5 w-2.5 rounded-full',
                    waConnected
                      ? 'bg-green-400 dark:bg-green-500'
                      : 'bg-red-400 dark:bg-red-500',
                  )}
                />
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {waConnected ? 'Connected' : 'Disconnected'}
                </span>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
