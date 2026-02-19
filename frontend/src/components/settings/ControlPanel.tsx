import { Pause, Play } from 'lucide-react'
import { useControlStatus, usePause, useResume } from '../../hooks/useControl'
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'

export function ControlPanel() {
  const { data: status, isLoading } = useControlStatus()
  const pause = usePause()
  const resume = useResume()

  const isPaused = status?.paused ?? false
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
          <div className="space-y-4">
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
        )}
      </CardContent>
    </Card>
  )
}
