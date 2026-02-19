import { useDashboard } from '../hooks/useDashboard'
import { usePipelineStatus } from '../hooks/usePipeline'
import { Spinner } from '../components/ui/Spinner'
import { StatsGrid } from '../components/dashboard/StatsGrid'
import { PipelineFunnel } from '../components/dashboard/PipelineFunnel'
import { TodayQuota } from '../components/dashboard/TodayQuota'
import { SystemStatus } from '../components/dashboard/SystemStatus'

export default function DashboardPage() {
  const { data: stats, isLoading: statsLoading } = useDashboard()
  const { data: pipeline, isLoading: pipelineLoading } = usePipelineStatus()

  if (statsLoading || pipelineLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }

  if (!stats || !pipeline) return null

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
        Dashboard
      </h1>

      <StatsGrid stats={stats} />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <PipelineFunnel status={pipeline} />
        </div>
        <div className="space-y-6">
          <TodayQuota
            quota={{
              messages_sent: stats.today_messages_sent,
              conversations_started: stats.today_conversations_started,
            }}
            limit={stats.daily_conversation_limit}
          />
          <SystemStatus />
        </div>
      </div>
    </div>
  )
}
