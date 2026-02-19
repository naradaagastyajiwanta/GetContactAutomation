import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card'
import { STATUS_COLORS, PIPELINE_STAGES } from '../../lib/constants'
import { formatNumber } from '../../lib/utils'
import type { PipelineStatus } from '../../lib/types'

interface PipelineFunnelProps {
  status: PipelineStatus
}

export function PipelineFunnel({ status }: PipelineFunnelProps) {
  const stages = PIPELINE_STAGES.filter((s) => s.key !== 'failed')
  const maxCount = Math.max(
    ...stages.map((s) => status[s.key as keyof PipelineStatus] as number),
    1,
  )

  return (
    <Card>
      <CardHeader>
        <CardTitle>Pipeline Funnel</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {stages.map((stage) => {
            const count = status[stage.key as keyof PipelineStatus] as number
            const width = Math.max((count / maxCount) * 100, 8)
            const colors = STATUS_COLORS[stage.key] || STATUS_COLORS.pending

            return (
              <div key={stage.key} className="flex items-center gap-3">
                <span className="w-24 shrink-0 text-sm text-gray-600 dark:text-gray-400">
                  {stage.label}
                </span>
                <div className="flex-1">
                  <div
                    className={`${colors.bg} ${colors.text} rounded px-2 py-1 text-xs font-medium transition-all`}
                    style={{ width: `${width}%` }}
                  >
                    {formatNumber(count)}
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        <div className="mt-4 flex items-center gap-2 border-t border-gray-200 pt-4 dark:border-gray-700">
          <span className="text-sm text-gray-500 dark:text-gray-400">Failed:</span>
          <span className={`${STATUS_COLORS.failed.bg} ${STATUS_COLORS.failed.text} rounded-full px-2.5 py-0.5 text-xs font-medium`}>
            {formatNumber(status.failed)}
          </span>
        </div>
      </CardContent>
    </Card>
  )
}
