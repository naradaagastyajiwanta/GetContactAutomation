import { Building2, Phone, MessageSquare, CheckCircle } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Card } from '../ui/Card'
import { formatNumber } from '../../lib/utils'
import type { DashboardStats } from '../../lib/types'

interface StatCardProps {
  icon: LucideIcon
  label: string
  value: number
  color: string
}

function StatCard({ icon: Icon, label, value, color }: StatCardProps) {
  return (
    <Card>
      <div className="flex items-center gap-4">
        <div className={`rounded-lg p-3 ${color}`}>
          <Icon className="h-6 w-6 text-white" />
        </div>
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400">{label}</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {formatNumber(value)}
          </p>
        </div>
      </div>
    </Card>
  )
}

interface StatsGridProps {
  stats: DashboardStats
}

export function StatsGrid({ stats }: StatsGridProps) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <StatCard
        icon={Building2}
        label="Total Universities"
        value={stats.total_universities}
        color="bg-blue-500"
      />
      <StatCard
        icon={Phone}
        label="IG Contacts Found"
        value={stats.total_contacts}
        color="bg-green-500"
      />
      <StatCard
        icon={MessageSquare}
        label="Active Conversations"
        value={stats.active_conversations}
        color="bg-yellow-500"
      />
      <StatCard
        icon={CheckCircle}
        label="Got Numbers"
        value={stats.successful_conversations}
        color="bg-emerald-600"
      />
    </div>
  )
}
