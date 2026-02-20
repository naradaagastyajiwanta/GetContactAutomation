import { Activity } from 'lucide-react'
import { useHealth } from '../../hooks/useHealth'
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card'
import { Spinner } from '../ui/Spinner'
import { cn } from '../../lib/utils'

export function HealthStatus() {
  const { data: health, isLoading } = useHealth()

  const waConnected = health?.whatsapp?.connected ?? false
  const igOk = health?.instagram?.ok ?? true
  const igError = health?.instagram?.error

  const igLabel: Record<string, string> = {
    suspended: 'Suspended',
    login_required: 'Session Expired',
  }

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

            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-500 dark:text-gray-400">Instagram Session</span>
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    'h-2.5 w-2.5 rounded-full',
                    igOk
                      ? 'bg-green-400 dark:bg-green-500'
                      : 'bg-red-400 dark:bg-red-500',
                  )}
                />
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {igOk ? 'Active' : (igError ? igLabel[igError] || igError : 'Error')}
                </span>
              </div>
            </div>

            {!igOk && (
              <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-3 mt-1">
                <p className="text-xs text-red-700 dark:text-red-400">
                  IG session is {igError === 'suspended' ? 'suspended by Instagram' : 'expired'}.
                  Update <span className="font-mono font-semibold">IG_SESSION_ID</span> in
                  Settings &gt; Config with a new session cookie from your browser.
                </p>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
