import { Building2, Phone, MessageSquare, CheckCircle } from 'lucide-react'
import { formatNumber } from '../../lib/utils'
import type { DashboardStats } from '../../lib/types'

interface StatsGridProps {
  stats: DashboardStats
}

interface MetricCardProps {
  icon: React.ReactNode
  label: string
  value: number
  sub?: string
  variant: 'indigo' | 'slate'
}

function MetricCard({ icon, label, value, sub, variant }: MetricCardProps) {
  const isIndigo = variant === 'indigo'
  return (
    <div className={`
      group relative overflow-hidden rounded-xl border bg-white px-5 py-4
      transition-all duration-200 hover:shadow-md hover:-translate-y-0.5
      dark:bg-gray-800/80
      ${isIndigo
        ? 'border-indigo-200 dark:border-indigo-800/50 hover:border-indigo-300 dark:hover:border-indigo-700'
        : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
      }
    `}>
      <div className="flex items-start justify-between">
        <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${
          isIndigo ? 'bg-indigo-100 dark:bg-indigo-900/40' : 'bg-gray-100 dark:bg-gray-700'
        }`}>
          {icon}
        </div>
      </div>
      <div className="mt-4">
        <p className="text-2xl font-bold tracking-tight text-gray-900 dark:text-white">
          {formatNumber(value)}
        </p>
        <p className="mt-1 text-xs font-medium text-gray-500 dark:text-gray-400">{label}</p>
        {sub && <p className="mt-0.5 text-[11px] text-gray-400 dark:text-gray-500">{sub}</p>}
      </div>
    </div>
  )
}

export function StatsGrid({ stats }: StatsGridProps) {
  const successRate = stats.total_contacts > 0
    ? ((stats.successful_conversations / stats.total_contacts) * 100).toFixed(1)
    : '0'

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <MetricCard
        icon={<Building2 className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />}
        label="Universities"
        value={stats.total_universities}
        sub={`${formatNumber(stats.universities_with_ig)} with IG`}
        variant="indigo"
      />
      <MetricCard
        icon={<Phone className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />}
        label="IG Contacts"
        value={stats.total_contacts}
        sub={`${formatNumber(stats.universities_with_phone)} with phones`}
        variant="slate"
      />
      <MetricCard
        icon={<MessageSquare className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />}
        label="Active Conv."
        value={stats.active_conversations}
        sub={`${formatNumber(stats.total_conversations)} total`}
        variant="slate"
      />
      <MetricCard
        icon={<CheckCircle className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />}
        label="Got Numbers"
        value={stats.successful_conversations}
        sub={`${successRate}% success rate`}
        variant="indigo"
      />
    </div>
  )
}
