import { cn } from '../../lib/utils'
import { TIMELINE_TRUNK, TIMELINE_BRANCHES, TIMELINE_TERMINALS } from '../../lib/constants'
import type { ConversationState } from '../../lib/types'

interface StateTimelineProps {
  currentState: ConversationState
}

type TimelinePosition =
  | { section: 'trunk'; index: number }
  | { section: 'branch'; branch: string; sub?: boolean }
  | { section: 'terminal' }

function getTimelinePosition(state: ConversationState): TimelinePosition {
  const trunkIdx = (TIMELINE_TRUNK as readonly string[]).indexOf(state)
  if (trunkIdx >= 0) return { section: 'trunk', index: trunkIdx }

  for (const branch of TIMELINE_BRANCHES) {
    if (branch.state === state) return { section: 'branch', branch: branch.state }
    if ('next' in branch && branch.next.state === state) return { section: 'branch', branch: branch.state, sub: true }
  }

  if ((TIMELINE_TERMINALS as readonly string[]).includes(state)) return { section: 'terminal' }
  return { section: 'trunk', index: -1 }
}

const BRANCH_STYLES = {
  green: {
    dot: 'bg-green-500 dark:bg-green-400',
    ring: 'ring-green-100 dark:ring-green-900/50',
    text: 'text-green-700 dark:text-green-300',
    line: 'bg-green-400 dark:bg-green-500',
  },
  orange: {
    dot: 'bg-orange-500 dark:bg-orange-400',
    ring: 'ring-orange-100 dark:ring-orange-900/50',
    text: 'text-orange-700 dark:text-orange-300',
    line: 'bg-orange-400 dark:bg-orange-500',
  },
  red: {
    dot: 'bg-red-500 dark:bg-red-400',
    ring: 'ring-red-100 dark:ring-red-900/50',
    text: 'text-red-700 dark:text-red-300',
    line: 'bg-red-400 dark:bg-red-500',
  },
} as const

const TERMINAL_STYLES: Record<string, { bg: string; text: string }> = {
  ABANDONED: { bg: 'bg-gray-200 dark:bg-gray-600', text: 'text-gray-600 dark:text-gray-300' },
  NO_REPLY: { bg: 'bg-gray-200 dark:bg-gray-600', text: 'text-gray-600 dark:text-gray-300' },
  UNDELIVERED: { bg: 'bg-red-100 dark:bg-red-900/50', text: 'text-red-700 dark:text-red-300' },
}

export function StateTimeline({ currentState }: StateTimelineProps) {
  const position = getTimelinePosition(currentState)

  // Determine how far along the trunk we are
  let trunkActiveIndex: number
  if (position.section === 'trunk') {
    trunkActiveIndex = position.index
  } else if (position.section === 'branch') {
    // If in a branch, trunk is fully completed
    trunkActiveIndex = TIMELINE_TRUNK.length - 1
  } else {
    // Terminal: find how far we got in trunk based on state order
    // Terminals can happen from anywhere, show trunk up to ANALYZING as gray
    trunkActiveIndex = TIMELINE_TRUNK.length - 1
  }

  const isInBranch = position.section === 'branch'
  const isTerminal = position.section === 'terminal'
  const activeBranch = isInBranch ? (position as { branch: string }).branch : null
  const isSubState = isInBranch && (position as { sub?: boolean }).sub

  return (
    <div className="overflow-x-auto">
      <div className="min-w-max py-2">
        {/* Trunk (horizontal) + Branches (vertical fork) */}
        <div className="flex items-start">
          {/* Trunk nodes */}
          <div className="flex items-center">
            {TIMELINE_TRUNK.map((state, idx) => {
              const isPast = idx < trunkActiveIndex
              const isCurrent = position.section === 'trunk' && idx === trunkActiveIndex
              const isCompleted = isPast || (idx <= trunkActiveIndex && position.section !== 'trunk')

              return (
                <div key={state} className="flex items-center">
                  {idx > 0 && (
                    <div
                      className={cn(
                        'h-0.5 w-6',
                        isCompleted || isCurrent
                          ? 'bg-indigo-500 dark:bg-indigo-400'
                          : 'bg-gray-300 dark:bg-gray-600',
                      )}
                    />
                  )}
                  <div className="flex flex-col items-center gap-1">
                    <div
                      className={cn(
                        'flex items-center justify-center rounded-full transition-colors',
                        isCurrent && 'h-4 w-4 bg-indigo-600 ring-4 ring-indigo-100 dark:bg-indigo-400 dark:ring-indigo-900/50',
                        isCompleted && !isCurrent && 'h-3 w-3 bg-indigo-500 dark:bg-indigo-400',
                        !isCompleted && !isCurrent && 'h-3 w-3 bg-gray-300 dark:bg-gray-600',
                      )}
                    />
                    <span
                      className={cn(
                        'text-[10px] leading-tight max-w-[60px] text-center',
                        isCurrent && 'font-semibold text-indigo-700 dark:text-indigo-300',
                        isCompleted && !isCurrent && 'text-gray-600 dark:text-gray-400',
                        !isCompleted && !isCurrent && 'text-gray-400 dark:text-gray-500',
                      )}
                    >
                      {state.replace(/_/g, ' ')}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Branch fork or Terminal badge */}
          {isTerminal ? (
            /* Terminal badge */
            <div className="flex items-center ml-1">
              <div className="h-0.5 w-4 bg-gray-300 dark:bg-gray-600" />
              <span
                className={cn(
                  'px-2 py-0.5 rounded text-[10px] font-semibold',
                  TERMINAL_STYLES[currentState]?.bg ?? 'bg-gray-200 dark:bg-gray-600',
                  TERMINAL_STYLES[currentState]?.text ?? 'text-gray-600 dark:text-gray-300',
                )}
              >
                {currentState.replace(/_/g, ' ')}
              </span>
            </div>
          ) : (
            /* Branch outcomes */
            <div className="flex flex-col gap-1.5 ml-1 pt-0">
              {TIMELINE_BRANCHES.map((branch, branchIdx) => {
                const style = BRANCH_STYLES[branch.color]
                const isActive = activeBranch === branch.state
                const isGrayed = !isInBranch // no branch active yet

                return (
                  <div key={branch.state} className="flex items-center">
                    {/* Connector from trunk */}
                    <div className="flex items-center">
                      {/* Vertical connector stub for non-first branches */}
                      <div className="relative">
                        <div
                          className={cn(
                            'h-0.5 w-4',
                            isActive ? style.line : 'bg-gray-300 dark:bg-gray-600',
                          )}
                        />
                        {/* Vertical line connecting branches */}
                        {branchIdx < TIMELINE_BRANCHES.length - 1 && (
                          <div
                            className={cn(
                              'absolute left-0 top-0.5 w-0.5 h-[calc(100%+6px)]',
                              isGrayed ? 'bg-gray-300 dark:bg-gray-600' : 'bg-gray-300 dark:bg-gray-600',
                            )}
                          />
                        )}
                      </div>
                    </div>

                    {/* Branch dot */}
                    <div
                      className={cn(
                        'flex-shrink-0 rounded-full transition-colors',
                        isActive ? cn('h-3.5 w-3.5 ring-3', style.dot, style.ring) : 'h-2.5 w-2.5',
                        !isActive && (isGrayed ? 'bg-gray-300 dark:bg-gray-600' : 'bg-gray-300 dark:bg-gray-600'),
                      )}
                    />

                    {/* Branch label */}
                    <span
                      className={cn(
                        'text-[10px] leading-tight ml-1.5 whitespace-nowrap',
                        isActive && !isSubState && cn('font-semibold', style.text),
                        isActive && isSubState && 'text-gray-600 dark:text-gray-400',
                        !isActive && 'text-gray-400 dark:text-gray-500',
                      )}
                    >
                      {branch.label}
                    </span>

                    {/* Sub-state for NEED_MORE → FOLLOWUP_SENT */}
                    {'next' in branch && (
                      <div className="flex items-center ml-1">
                        <div
                          className={cn(
                            'h-0.5 w-3',
                            isActive ? style.line : 'bg-gray-300 dark:bg-gray-600',
                          )}
                        />
                        <div
                          className={cn(
                            'flex-shrink-0 rounded-full transition-colors',
                            isActive && isSubState ? cn('h-3.5 w-3.5 ring-3', style.dot, style.ring) : 'h-2.5 w-2.5',
                            isActive && !isSubState ? style.dot : '',
                            !isActive && 'bg-gray-300 dark:bg-gray-600',
                          )}
                        />
                        <span
                          className={cn(
                            'text-[10px] leading-tight ml-1 whitespace-nowrap',
                            isActive && isSubState && cn('font-semibold', style.text),
                            isActive && !isSubState && style.text,
                            !isActive && 'text-gray-400 dark:text-gray-500',
                          )}
                        >
                          {branch.next.label}
                        </span>
                        {/* Loop indicator */}
                        <span
                          className={cn(
                            'text-xs ml-0.5',
                            isActive ? style.text : 'text-gray-400 dark:text-gray-500',
                          )}
                          title="Loops back to Waiting Reply"
                        >
                          ↩
                        </span>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
