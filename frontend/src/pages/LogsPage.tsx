import { useState, useEffect, useRef, useCallback } from 'react'
import { Terminal, Trash2, PauseCircle, PlayCircle, ArrowDown } from 'lucide-react'
import { useSystemLogs } from '../hooks/useSystemLogs'
import { Spinner } from '../components/ui/Spinner'
import type { LogLineEntry } from '../hooks/useWebSocket'

const LEVEL_CLASS: Record<string, string> = {
  DEBUG:    'text-gray-500',
  INFO:     'text-green-400',
  WARNING:  'text-yellow-400',
  WARN:     'text-yellow-400',
  ERROR:    'text-red-400',
  CRITICAL: 'text-red-600',
}

const FILTER_OPTIONS = ['ALL', 'INFO', 'WARNING', 'ERROR'] as const
type FilterLevel = (typeof FILTER_OPTIONS)[number]

function matchesFilter(entry: LogLineEntry, filter: FilterLevel): boolean {
  if (filter === 'ALL') return true
  if (filter === 'ERROR') return entry.level === 'ERROR' || entry.level === 'CRITICAL'
  if (filter === 'WARNING') return entry.level === 'WARNING' || entry.level === 'WARN'
  return entry.level === filter
}

export default function LogsPage() {
  const { lines, loading, error, clear } = useSystemLogs()
  const [filter, setFilter] = useState<FilterLevel>('ALL')
  const [paused, setPaused] = useState(false)
  const [atBottom, setAtBottom] = useState(true)
  const [frozenLines, setFrozenLines] = useState<LogLineEntry[]>([])

  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // When paused, snapshot the current lines so display doesn't move
  useEffect(() => {
    if (paused) {
      setFrozenLines(lines)
    }
  }, [paused, lines])

  const displayed = paused ? frozenLines : lines
  const filtered = displayed.filter(e => matchesFilter(e, filter))

  // Auto-scroll to bottom unless user scrolled up
  useEffect(() => {
    if (!paused && atBottom) {
      bottomRef.current?.scrollIntoView({ behavior: 'instant' })
    }
  }, [filtered.length, paused, atBottom])

  const handleScroll = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    const threshold = 60
    const isBottom = el.scrollHeight - el.scrollTop - el.clientHeight < threshold
    setAtBottom(isBottom)
  }, [])

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    setAtBottom(true)
  }, [])

  const errorCount = lines.filter(e => e.level === 'ERROR' || e.level === 'CRITICAL').length
  const warnCount = lines.filter(e => e.level === 'WARNING' || e.level === 'WARN').length

  return (
    <div className="flex flex-col h-[calc(100vh-7rem)] gap-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Terminal className="h-5 w-5 text-gray-400" />
          <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">System Logs</h1>
          <span className="text-xs text-gray-500 dark:text-gray-400">({lines.length} lines)</span>
          {errorCount > 0 && (
            <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400">
              {errorCount} errors
            </span>
          )}
          {warnCount > 0 && (
            <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400">
              {warnCount} warnings
            </span>
          )}
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2">
          {/* Level filter */}
          <div className="flex rounded-md overflow-hidden border border-gray-700 text-xs">
            {FILTER_OPTIONS.map(lvl => (
              <button
                key={lvl}
                onClick={() => setFilter(lvl)}
                className={`px-2.5 py-1 transition-colors ${
                  filter === lvl
                    ? 'bg-gray-700 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-200'
                }`}
              >
                {lvl}
              </button>
            ))}
          </div>

          {/* Pause / Resume */}
          <button
            onClick={() => setPaused(p => !p)}
            title={paused ? 'Resume live updates' : 'Pause live updates'}
            className="flex items-center gap-1 rounded px-2.5 py-1 text-xs border border-gray-700 bg-gray-800 text-gray-300 hover:bg-gray-700 transition-colors"
          >
            {paused
              ? <><PlayCircle className="h-3.5 w-3.5 text-green-400" /> Resume</>
              : <><PauseCircle className="h-3.5 w-3.5 text-yellow-400" /> Pause</>
            }
          </button>

          {/* Clear */}
          <button
            onClick={clear}
            title="Clear log display"
            className="flex items-center gap-1 rounded px-2.5 py-1 text-xs border border-gray-700 bg-gray-800 text-gray-300 hover:bg-gray-700 transition-colors"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Clear
          </button>
        </div>
      </div>

      {/* Terminal window */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="relative flex-1 overflow-y-auto rounded-lg bg-gray-950 border border-gray-800 p-3 font-mono text-xs leading-5"
      >
        {loading && (
          <div className="flex items-center gap-2 text-gray-500 p-4">
            <Spinner size="sm" />
            <span>Loading logs...</span>
          </div>
        )}

        {error && !loading && (
          <p className="text-red-400 p-2">Failed to load logs: {error}</p>
        )}

        {!loading && filtered.length === 0 && (
          <p className="text-gray-600 p-2 italic">No log lines yet...</p>
        )}

        {filtered.map((entry, i) => (
          <div key={i} className="flex gap-2 hover:bg-gray-900/50 px-1 rounded">
            <span className="shrink-0 text-gray-600 select-none">{entry.ts}</span>
            <span className={`shrink-0 w-16 font-bold ${LEVEL_CLASS[entry.level] ?? 'text-gray-400'}`}>
              {entry.level}
            </span>
            <span className="text-gray-300 break-all">{entry.text.split(': ').slice(1).join(': ') || entry.text}</span>
          </div>
        ))}

        <div ref={bottomRef} />
      </div>

      {/* Scroll-to-bottom FAB */}
      {!atBottom && (
        <button
          onClick={scrollToBottom}
          className="fixed bottom-8 right-8 z-50 flex items-center gap-1.5 rounded-full bg-indigo-600 px-3 py-2 text-xs text-white shadow-lg hover:bg-indigo-700 transition-colors"
        >
          <ArrowDown className="h-3.5 w-3.5" />
          Jump to bottom
        </button>
      )}
    </div>
  )
}
