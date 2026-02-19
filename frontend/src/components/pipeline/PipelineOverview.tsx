import { Clock, Search, Download, MessageSquare, CheckCircle, XCircle } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Card } from '../ui/Card'
import { Badge } from '../ui/Badge'
import { STATUS_COLORS } from '../../lib/constants'
import { formatNumber } from '../../lib/utils'
import type { PipelineStatus } from '../../lib/types'

const ICON_MAP: Record<string, LucideIcon> = {
  Clock,
  Search,
  Download,
  MessageSquare,
  CheckCircle,
  XCircle,
}

const stages: { key: keyof PipelineStatus; label: string; icon: string }[] = [
  { key: 'pending', label: 'Pending', icon: 'Clock' },
  { key: 'ig_found', label: 'IG Found', icon: 'Search' },
  { key: 'ig_scraped', label: 'Scraped', icon: 'Download' },
  { key: 'contacted', label: 'Contacted', icon: 'MessageSquare' },
  { key: 'got_number', label: 'Got Number', icon: 'CheckCircle' },
  { key: 'failed', label: 'Failed', icon: 'XCircle' },
]

interface PipelineOverviewProps {
  status: PipelineStatus
}

export function PipelineOverview({ status }: PipelineOverviewProps) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {stages.map((stage) => {
          const Icon = ICON_MAP[stage.icon] || Clock
          const colors = STATUS_COLORS[stage.key] || STATUS_COLORS.pending
          const count = status[stage.key] as number

          return (
            <Card key={stage.key}>
              <div className="flex flex-col items-center text-center">
                <Badge className={`${colors.bg} ${colors.text} mb-2`}>
                  <Icon className="mr-1 h-3 w-3" />
                  {stage.label}
                </Badge>
                <span className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                  {formatNumber(count)}
                </span>
              </div>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
