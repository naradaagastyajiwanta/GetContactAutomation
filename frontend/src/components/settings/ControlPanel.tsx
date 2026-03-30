import { Pause, Play, MessageSquare, Video, Brain } from 'lucide-react'
import { useControlStatus, usePause, useResume, useToggleChatbot } from '../../hooks/useControl'
import { Card, CardContent } from '../ui/Card'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { cn } from '../../lib/utils'

function Toggle({
  enabled,
  loading,
  onToggle,
}: {
  enabled: boolean
  loading: boolean
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      disabled={loading}
      onClick={onToggle}
      className={cn(
        'relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:focus:ring-offset-gray-800',
        enabled ? 'bg-indigo-600' : 'bg-gray-200 dark:bg-gray-600',
      )}
    >
      <span
        className={cn(
          'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200',
          enabled ? 'translate-x-5' : 'translate-x-0',
        )}
      />
    </button>
  )
}

function ToggleRow({
  icon,
  label,
  description,
  enabled,
  loading,
  onToggle,
}: {
  icon: React.ReactNode
  label: string
  description?: string
  enabled: boolean
  loading: boolean
  onToggle: () => void
}) {
  return (
    <div
      className={cn(
        'flex items-center justify-between rounded-lg border px-4 py-3 transition-colors',
        enabled
          ? 'border-indigo-200 bg-indigo-50/50 dark:border-indigo-800 dark:bg-indigo-900/20'
          : 'border-gray-200 bg-gray-50/50 dark:border-gray-700 dark:bg-gray-800/50',
      )}
    >
      <div className="flex items-center gap-3">
        <div
          className={cn(
            'flex h-8 w-8 items-center justify-center rounded-lg',
            enabled
              ? 'bg-indigo-100 text-indigo-600 dark:bg-indigo-900/40 dark:text-indigo-400'
              : 'bg-gray-100 text-gray-400 dark:bg-gray-700 dark:text-gray-500',
          )}
        >
          {icon}
        </div>
        <div>
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{label}</span>
          {description && (
            <p className="text-xs text-gray-400 dark:text-gray-500">{description}</p>
          )}
        </div>
      </div>
      <Toggle enabled={enabled} loading={loading} onToggle={onToggle} />
    </div>
  )
}

export function ControlPanel() {
  const { data: status, isLoading } = useControlStatus()
  const pause = usePause()
  const resume = useResume()
  const toggleChatbot = useToggleChatbot()

  const isPaused = status?.paused ?? false
  const chatbotEnabled = status?.chatbot_enabled ?? true
  const audiensiEnabled = status?.audiensi_enabled ?? false
  const researchMultiAgent = status?.research_multi_agent ?? false
  const isToggling = pause.isPending || resume.isPending

  return (
    <Card
      padding={false}
      className={cn(
        'overflow-hidden transition-colors',
        isPaused && 'ring-2 ring-yellow-300 dark:ring-yellow-600',
      )}
    >
      {/* Status banner */}
      <div
        className={cn(
          'flex items-center justify-between px-5 py-3',
          isPaused
            ? 'bg-yellow-50 dark:bg-yellow-900/20'
            : 'bg-green-50 dark:bg-green-900/20',
        )}
      >
        <div className="flex items-center gap-2.5">
          <span className="relative flex h-3 w-3">
            <span
              className={cn(
                'absolute inline-flex h-full w-full rounded-full opacity-75',
                isPaused ? 'bg-yellow-400' : 'animate-ping bg-green-400',
              )}
            />
            <span
              className={cn(
                'relative inline-flex h-3 w-3 rounded-full',
                isPaused ? 'bg-yellow-400' : 'bg-green-500',
              )}
            />
          </span>
          <span
            className={cn(
              'text-sm font-semibold',
              isPaused
                ? 'text-yellow-700 dark:text-yellow-400'
                : 'text-green-700 dark:text-green-400',
            )}
          >
            {isPaused ? 'Bot is Paused' : 'Bot is Running'}
          </span>
        </div>
        <Button
          variant={isPaused ? 'primary' : 'danger'}
          size="sm"
          loading={isToggling}
          onClick={() => (isPaused ? resume.mutate() : pause.mutate())}
        >
          {isPaused ? (
            <>
              <Play className="h-4 w-4" />
              Resume
            </>
          ) : (
            <>
              <Pause className="h-4 w-4" />
              Pause
            </>
          )}
        </Button>
      </div>

      <CardContent className="space-y-3 p-5">
        {isLoading ? (
          <div className="flex justify-center py-4">
            <Spinner size="md" />
          </div>
        ) : (
          <>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
              Features
            </p>
            <ToggleRow
              icon={<MessageSquare className="h-4 w-4" />}
              label="Contact Finder"
              description="Auto WA outreach untuk cari kontak"
              enabled={chatbotEnabled}
              loading={toggleChatbot.isPending}
              onToggle={() => toggleChatbot.mutate({ type: 'agent', enabled: !chatbotEnabled })}
            />
            <ToggleRow
              icon={<Video className="h-4 w-4" />}
              label="Audiensi"
              description="Penjadwalan audiensi otomatis"
              enabled={audiensiEnabled}
              loading={toggleChatbot.isPending}
              onToggle={() => toggleChatbot.mutate({ type: 'audiensi', enabled: !audiensiEnabled })}
            />
            <ToggleRow
              icon={<Brain className="h-4 w-4" />}
              label="Multi-Agent Research"
              description="1 pertanyaan = 1 agent + reviewer"
              enabled={researchMultiAgent}
              loading={toggleChatbot.isPending}
              onToggle={() => toggleChatbot.mutate({ type: 'research_multi_agent', enabled: !researchMultiAgent })}
            />
          </>
        )}
      </CardContent>
    </Card>
  )
}
