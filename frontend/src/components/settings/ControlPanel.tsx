import { Pause, Play, MessageSquare, Video, Brain } from 'lucide-react'
import { useControlStatus, usePause, useResume, useToggleChatbot } from '../../hooks/useControl'
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'

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
      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:focus:ring-offset-gray-800 ${
        enabled ? 'bg-indigo-600' : 'bg-gray-200 dark:bg-gray-600'
      }`}
    >
      <span
        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ${
          enabled ? 'translate-x-5' : 'translate-x-0'
        }`}
      />
    </button>
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
    <Card>
      <CardHeader>
        <CardTitle>Bot Control</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex justify-center py-4">
            <Spinner size="md" />
          </div>
        ) : (
          <div className="space-y-5">
            {/* Master pause/resume */}
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <span
                  className={`h-3 w-3 rounded-full ${
                    isPaused
                      ? 'bg-yellow-400 dark:bg-yellow-500'
                      : 'bg-green-400 dark:bg-green-500'
                  }`}
                />
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  {isPaused ? 'Bot is paused' : 'Bot is running'}
                </span>
              </div>

              <Button
                variant={isPaused ? 'primary' : 'danger'}
                size="lg"
                className="w-full"
                loading={isToggling}
                onClick={() => (isPaused ? resume.mutate() : pause.mutate())}
              >
                {isPaused ? (
                  <>
                    <Play className="h-5 w-5" />
                    Resume Bot
                  </>
                ) : (
                  <>
                    <Pause className="h-5 w-5" />
                    Pause Bot
                  </>
                )}
              </Button>
            </div>

            {/* Chatbot toggles */}
            <div className="border-t border-gray-200 pt-4 dark:border-gray-700">
              <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Chatbot Toggles
              </p>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <MessageSquare className="h-4 w-4 text-gray-500 dark:text-gray-400" />
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      Contact Finder
                    </span>
                  </div>
                  <Toggle
                    enabled={chatbotEnabled}
                    loading={toggleChatbot.isPending}
                    onToggle={() =>
                      toggleChatbot.mutate({ type: 'agent', enabled: !chatbotEnabled })
                    }
                  />
                </div>

                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Video className="h-4 w-4 text-gray-500 dark:text-gray-400" />
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      Audiensi
                    </span>
                  </div>
                  <Toggle
                    enabled={audiensiEnabled}
                    loading={toggleChatbot.isPending}
                    onToggle={() =>
                      toggleChatbot.mutate({ type: 'audiensi', enabled: !audiensiEnabled })
                    }
                  />
                </div>

                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Brain className="h-4 w-4 text-gray-500 dark:text-gray-400" />
                    <div>
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        Multi-Agent Research
                      </span>
                      <p className="text-xs text-gray-400 dark:text-gray-500">
                        1 pertanyaan = 1 agent + reviewer
                      </p>
                    </div>
                  </div>
                  <Toggle
                    enabled={researchMultiAgent}
                    loading={toggleChatbot.isPending}
                    onToggle={() =>
                      toggleChatbot.mutate({ type: 'research_multi_agent', enabled: !researchMultiAgent })
                    }
                  />
                </div>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
