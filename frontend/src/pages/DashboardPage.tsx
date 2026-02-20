import { Link } from 'react-router-dom'
import { Lightbulb } from 'lucide-react'
import { useDashboard } from '../hooks/useDashboard'
import { usePipelineStatus } from '../hooks/usePipeline'
import { useLearningStats } from '../hooks/useLearning'
import { Spinner } from '../components/ui/Spinner'
import { Card } from '../components/ui/Card'
import { StatsGrid } from '../components/dashboard/StatsGrid'
import { PipelineFunnel } from '../components/dashboard/PipelineFunnel'
import { TodayQuota } from '../components/dashboard/TodayQuota'
import { SystemStatus } from '../components/dashboard/SystemStatus'

export default function DashboardPage() {
  const { data: stats, isLoading: statsLoading } = useDashboard()
  const { data: pipeline, isLoading: pipelineLoading } = usePipelineStatus()
  const { data: learningStats } = useLearningStats()

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
          {learningStats && (
            <Card>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Lightbulb className="h-5 w-5 text-amber-500" />
                  <h3 className="font-semibold text-gray-900 dark:text-gray-100">Learning</h3>
                </div>
                <Link to="/learning" className="text-xs text-indigo-600 hover:text-indigo-800 dark:text-indigo-400">
                  View all
                </Link>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{learningStats.total_active_lessons}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Lessons</p>
                </div>
                <div>
                  <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{learningStats.unprocessed_analyses}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Pending Analyses</p>
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
