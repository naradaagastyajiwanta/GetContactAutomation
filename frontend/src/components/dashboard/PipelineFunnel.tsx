import { Card } from '../ui/Card'
import { PIPELINE_STAGES } from '../../lib/constants'
import { formatNumber } from '../../lib/utils'
import type { PipelineStatus } from '../../lib/types'

interface PipelineFunnelProps {
  status: PipelineStatus
}

const STAGE_BG = [
  'bg-gray-50 dark:bg-gray-800/50',
  'bg-gray-50 dark:bg-gray-800/50',
  'bg-indigo-50 dark:bg-indigo-950/30',
  'bg-indigo-50 dark:bg-indigo-950/30',
  'bg-indigo-50 dark:bg-indigo-950/30',
]
const STAGE_TEXT = [
  'text-gray-700 dark:text-gray-300',
  'text-gray-700 dark:text-gray-300',
  'text-indigo-700 dark:text-indigo-300',
  'text-indigo-700 dark:text-indigo-300',
  'text-indigo-700 dark:text-indigo-300',
]
const STAGE_BAR = [
  'bg-gray-300 dark:bg-gray-600',
  'bg-gray-300 dark:bg-gray-600',
  'bg-indigo-400 dark:bg-indigo-600',
  'bg-indigo-400 dark:bg-indigo-600',
  'bg-indigo-400 dark:bg-indigo-600',
]
const STAGE_DOT = [
  'bg-gray-400',
  'bg-gray-400',
  'bg-indigo-500 dark:bg-indigo-400',
  'bg-indigo-500 dark:bg-indigo-400',
  'bg-indigo-500 dark:bg-indigo-400',
]

export function PipelineFunnel({ status }: PipelineFunnelProps) {
  const stages = PIPELINE_STAGES
  const maxCount = Math.max(
    ...stages.map((s) => status[s.key as keyof PipelineStatus] as number),
    1,
  )
  const total = stages.reduce((sum, s) => sum + ((status[s.key as keyof PipelineStatus] as number) || 0), 0)

  return (
    <Card>
      <div className="border-b border-gray-100 px-5 py-4 dark:border-gray-800">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Pipeline Overview</h3>
            <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
              {formatNumber(total)} total in pipeline
            </p>
          </div>
        </div>
      </div>

      <div className="p-5">
        {/* Stage bars */}
        <div className="space-y-2">
          {stages.map((stage, idx) => {
            const count = (status[stage.key as keyof PipelineStatus] as number) || 0
            const pct = maxCount > 0 ? (count / maxCount) * 100 : 0

            return (
              <div key={stage.key} className="flex items-center gap-3">
                <span className="w-20 shrink-0 text-xs font-medium text-gray-500 dark:text-gray-400">
                  {stage.label}
                </span>
                <div className="flex-1">
                  <div className="flex items-center gap-3">
                    <div className="h-7 flex-1 overflow-hidden rounded-md bg-gray-100 dark:bg-gray-800">
                      <div
                        className={`flex h-full items-center justify-end rounded-md px-2 transition-all duration-500 ${STAGE_BG[idx]} ${STAGE_BAR[idx]}`}
                        style={{ width: `${Math.max(pct, 2)}%` }}
                      >
                        <span className={`text-xs font-bold ${STAGE_TEXT[idx]}`}>
                          {count > 0 ? formatNumber(count) : ''}
                        </span>
                      </div>
                    </div>
                    <span className="w-10 text-right text-xs font-medium text-gray-400 dark:text-gray-500">
                      {pct.toFixed(0)}%
                    </span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {/* Failed */}
        <div className="mt-4 flex items-center justify-between rounded-lg border border-gray-200 bg-gray-50 px-4 py-2.5 dark:border-gray-700 dark:bg-gray-800/50">
          <span className="text-xs text-gray-500 dark:text-gray-400">Failed outreach</span>
          <span className="text-sm font-bold text-gray-700 dark:text-gray-300">
            {formatNumber(status.failed)}
          </span>
        </div>
      </div>
    </Card>
  )
}
