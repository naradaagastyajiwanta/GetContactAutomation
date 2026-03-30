import {
  CalendarDays,
  CalendarCheck,
  ClipboardList,
  CheckCircle,
  Users,
  Building2,
} from 'lucide-react'
import { Card } from '../ui/Card'
import { Spinner } from '../ui/Spinner'
import { formatNumber } from '../../lib/utils'
import type { DmsStats } from '../../api/dms'

interface Props {
  stats: DmsStats | undefined
  isLoading: boolean
}

const cards = [
  {
    key: 'total_schedules' as const,
    label: 'Total Schedules',
    icon: CalendarDays,
    color: 'text-blue-600 dark:text-blue-400',
    bg: 'bg-blue-50 dark:bg-blue-900/30',
  },
  {
    key: 'today_schedules' as const,
    label: 'Today',
    icon: CalendarCheck,
    color: 'text-emerald-600 dark:text-emerald-400',
    bg: 'bg-emerald-50 dark:bg-emerald-900/30',
  },
  {
    key: 'total_followups' as const,
    label: 'Follow-ups',
    icon: ClipboardList,
    color: 'text-indigo-600 dark:text-indigo-400',
    bg: 'bg-indigo-50 dark:bg-indigo-900/30',
  },
  {
    key: 'total_contacts' as const,
    label: 'PIC Contacts',
    icon: Users,
    color: 'text-amber-600 dark:text-amber-400',
    bg: 'bg-amber-50 dark:bg-amber-900/30',
  },
  {
    key: 'total_universities' as const,
    label: 'Universities',
    icon: Building2,
    color: 'text-purple-600 dark:text-purple-400',
    bg: 'bg-purple-50 dark:bg-purple-900/30',
  },
]

export function DmsStatsCards({ stats, isLoading }: Props) {
  if (isLoading) {
    return (
      <div className="flex justify-center py-6">
        <Spinner size="lg" />
      </div>
    )
  }

  const approved = stats?.approval_stats?.['Approved'] ?? 0

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
      {cards.map((c) => {
        const Icon = c.icon
        const value = stats ? (stats[c.key] as number) : 0
        return (
          <Card key={c.key} className="flex items-center gap-3">
            <div className={`rounded-lg p-2 ${c.bg}`}>
              <Icon className={`h-5 w-5 ${c.color}`} />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                {formatNumber(value)}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{c.label}</p>
            </div>
          </Card>
        )
      })}

      {/* Approved card */}
      <Card className="flex items-center gap-3">
        <div className="rounded-lg bg-green-50 p-2 dark:bg-green-900/30">
          <CheckCircle className="h-5 w-5 text-green-600 dark:text-green-400" />
        </div>
        <div>
          <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {formatNumber(approved)}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400">Approved</p>
        </div>
      </Card>
    </div>
  )
}
