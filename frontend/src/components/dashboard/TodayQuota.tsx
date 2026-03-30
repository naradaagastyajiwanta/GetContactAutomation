import { MessageSquare } from 'lucide-react'
import { Card } from '../ui/Card'
import { formatNumber } from '../../lib/utils'

interface TodayQuotaProps {
  quota: {
    messages_sent: number
    conversations_started: number
  }
  limit?: number
}

export function TodayQuota({ quota, limit = 20 }: TodayQuotaProps) {
  const pct = Math.min((quota.conversations_started / limit) * 100, 100)
  const remaining = Math.max(limit - quota.conversations_started, 0)

  const r = 34
  const c = 2 * Math.PI * r
  const dashOffset = c - (pct / 100) * c
  const ringColor = pct >= 90 ? '#94a3b8' : '#6366f1'

  return (
    <Card>
      <div className="border-b border-gray-100 px-5 py-3 dark:border-gray-800">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Today's Progress</h3>
      </div>
      <div className="p-5">
        <div className="flex items-center gap-5">
          {/* Circular ring */}
          <div className="relative flex shrink-0 items-center justify-center">
            <svg width="80" height="80" className="-rotate-90">
              <circle cx="40" cy="40" r={r} fill="none" stroke="currentColor" strokeWidth="5" className="text-gray-100 dark:text-gray-800" />
              <circle
                cx="40" cy="40" r={r} fill="none" stroke={ringColor} strokeWidth="5"
                strokeLinecap="round" strokeDasharray={c} strokeDashoffset={dashOffset}
                className="transition-all duration-700"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-xl font-bold text-gray-900 dark:text-white">{pct.toFixed(0)}%</span>
            </div>
          </div>

          {/* Stats */}
          <div className="flex-1 space-y-3">
            <div className="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-800/50">
              <span className="text-xs text-gray-500 dark:text-gray-400">Conversations</span>
              <span className="text-sm font-bold text-gray-900 dark:text-white">
                {formatNumber(quota.conversations_started)}<span className="text-xs font-normal text-gray-400">/{limit}</span>
              </span>
            </div>
            <div className="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-800/50">
              <div className="flex items-center gap-1.5">
                <MessageSquare className="h-3.5 w-3.5 text-gray-400" />
                <span className="text-xs text-gray-500 dark:text-gray-400">Messages sent</span>
              </div>
              <span className="text-sm font-bold text-gray-900 dark:text-white">{formatNumber(quota.messages_sent)}</span>
            </div>
            <div className="flex items-center justify-between rounded-lg bg-indigo-50 px-3 py-2 dark:bg-indigo-950/20">
              <span className="text-xs text-indigo-600 dark:text-indigo-400">Remaining today</span>
              <span className="text-sm font-bold text-indigo-600 dark:text-indigo-400">{formatNumber(remaining)}</span>
            </div>
          </div>
        </div>
      </div>
    </Card>
  )
}
