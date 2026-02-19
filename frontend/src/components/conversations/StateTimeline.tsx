import { cn } from '../../lib/utils'
import { CONVERSATION_STATES } from '../../lib/constants'
import type { ConversationState } from '../../lib/types'

interface StateTimelineProps {
  currentState: ConversationState
}

export function StateTimeline({ currentState }: StateTimelineProps) {
  const currentIndex = CONVERSATION_STATES.indexOf(currentState)

  return (
    <div className="overflow-x-auto">
      <div className="flex items-center gap-0 min-w-max py-2">
        {CONVERSATION_STATES.map((state, idx) => {
          const isCurrent = idx === currentIndex
          const isPast = idx < currentIndex
          const isFuture = idx > currentIndex

          return (
            <div key={state} className="flex items-center">
              {idx > 0 && (
                <div
                  className={cn(
                    'h-0.5 w-6',
                    isPast || isCurrent
                      ? 'bg-indigo-500 dark:bg-indigo-400'
                      : 'bg-gray-300 dark:bg-gray-600',
                  )}
                />
              )}
              <div className="flex flex-col items-center gap-1">
                <div
                  className={cn(
                    'flex h-3 w-3 items-center justify-center rounded-full transition-colors',
                    isCurrent && 'h-4 w-4 bg-indigo-600 ring-4 ring-indigo-100 dark:bg-indigo-400 dark:ring-indigo-900/50',
                    isPast && 'bg-indigo-500 dark:bg-indigo-400',
                    isFuture && 'bg-gray-300 dark:bg-gray-600',
                  )}
                />
                <span
                  className={cn(
                    'text-[10px] leading-tight max-w-[60px] text-center',
                    isCurrent && 'font-semibold text-indigo-700 dark:text-indigo-300',
                    isPast && 'text-gray-600 dark:text-gray-400',
                    isFuture && 'text-gray-400 dark:text-gray-500',
                  )}
                >
                  {state.replace(/_/g, ' ')}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
