import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card'

interface TodayQuotaProps {
  quota: {
    messages_sent: number
    conversations_started: number
  }
  limit?: number
}

export function TodayQuota({ quota, limit = 20 }: TodayQuotaProps) {
  const percentage = Math.min((quota.conversations_started / limit) * 100, 100)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Today's Quota</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div>
            <div className="mb-1 flex items-center justify-between text-sm">
              <span className="text-gray-600 dark:text-gray-400">
                Conversations started
              </span>
              <span className="font-medium text-gray-900 dark:text-gray-100">
                {quota.conversations_started}/{limit}
              </span>
            </div>
            <div className="h-3 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
              <div
                className="h-full rounded-full bg-indigo-500 transition-all"
                style={{ width: `${percentage}%` }}
              />
            </div>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {percentage.toFixed(0)}% of daily limit
            </p>
          </div>

          <div className="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-700/50">
            <span className="text-sm text-gray-600 dark:text-gray-400">
              Messages sent today
            </span>
            <span className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              {quota.messages_sent}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
