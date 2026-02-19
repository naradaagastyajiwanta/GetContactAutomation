import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card'
import { STATUS_COLORS } from '../../lib/constants'
import { formatNumber } from '../../lib/utils'
import type { PipelineStatus } from '../../lib/types'

const stages: { key: keyof PipelineStatus; label: string }[] = [
  { key: 'pending', label: 'Pending' },
  { key: 'ig_found', label: 'IG Found' },
  { key: 'ig_scraped', label: 'Scraped' },
  { key: 'contacted', label: 'Contacted' },
  { key: 'got_number', label: 'Got Number' },
]

interface FunnelChartProps {
  status: PipelineStatus
}

export function FunnelChart({ status }: FunnelChartProps) {
  const maxCount = Math.max(
    ...stages.map((s) => status[s.key] as number),
    1,
  )

  return (
    <Card>
      <CardHeader>
        <CardTitle>Pipeline Flow</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {stages.map((stage, index) => {
            const count = status[stage.key] as number
            const width = Math.max((count / maxCount) * 100, 6)
            const colors = STATUS_COLORS[stage.key] || STATUS_COLORS.pending

            return (
              <div key={stage.key}>
                <div className="mb-1 flex items-center justify-between text-xs">
                  <span className="text-gray-600 dark:text-gray-400">
                    {index + 1}. {stage.label}
                  </span>
                  <span className="font-medium text-gray-900 dark:text-gray-100">
                    {formatNumber(count)}
                  </span>
                </div>
                <div className="h-6 w-full overflow-hidden rounded bg-gray-100 dark:bg-gray-700">
                  <div
                    className={`${colors.bg} ${colors.text} flex h-full items-center rounded px-2 text-xs font-medium transition-all`}
                    style={{ width: `${width}%` }}
                  >
                    {width > 15 ? formatNumber(count) : ''}
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        <div className="mt-4 flex items-center gap-2 border-t border-gray-200 pt-4 dark:border-gray-700">
          <span className="text-sm text-gray-500 dark:text-gray-400">Failed:</span>
          <span
            className={`${STATUS_COLORS.failed.bg} ${STATUS_COLORS.failed.text} rounded-full px-2.5 py-0.5 text-xs font-medium`}
          >
            {formatNumber(status.failed)}
          </span>
        </div>
      </CardContent>
    </Card>
  )
}
