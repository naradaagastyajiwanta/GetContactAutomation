import { TrendingUp, Phone } from 'lucide-react'
import { Card } from '../ui/Card'
import { type PhoneNumberStats } from '../../api/phoneNumbers'

interface PhoneNumberStatsProps {
  stats: PhoneNumberStats | undefined
  isLoading: boolean
}

export function PhoneNumberStatsCard({ stats, isLoading }: PhoneNumberStatsProps) {
  if (isLoading || !stats) {
    return (
      <Card>
        <div className="p-6">
          <div className="h-24 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
        </div>
      </Card>
    )
  }

  const isPositiveChange = stats.percent_change >= 0
  const changeColor = isPositiveChange ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
  const changeBgColor = isPositiveChange 
    ? 'bg-green-100 dark:bg-green-900/30' 
    : 'bg-red-100 dark:bg-red-900/30'

  return (
    <Card>
      <div className="p-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Total Count */}
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Total Numbers</p>
              <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-gray-100">
                {stats.total_count.toLocaleString()}
              </p>
            </div>
            <Phone className="h-8 w-8 text-blue-600 dark:text-blue-400 opacity-50" />
          </div>

          {/* Today's Additions */}
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Added Today</p>
              <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-gray-100">
                +{stats.today_count}
              </p>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Previous day: {stats.yesterday_count}
              </p>
            </div>
          </div>

          {/* Growth Percentage */}
          <div className={`flex items-start justify-between rounded-lg ${changeBgColor} p-4`}>
            <div>
              <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Growth vs Yesterday</p>
              <div className="mt-2 flex items-baseline gap-2">
                <p className={`text-3xl font-bold ${changeColor}`}>
                  {isPositiveChange ? '+' : ''}{stats.percent_change}%
                </p>
                <TrendingUp className={`h-5 w-5 ${changeColor}`} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </Card>
  )
}
