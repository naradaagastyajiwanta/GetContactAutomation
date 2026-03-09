import { useState } from 'react'
import { Clock, CheckCircle, XCircle, Loader2, ChevronDown, ChevronUp, Timer, Cpu, Calendar } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card'
import { usePipelineLogs } from '../../hooks/usePipeline'
import type { PipelineLog, PipelineAgentType, PipelineLogStatus } from '../../lib/types'

const AGENT_LABELS: Record<PipelineAgentType, string> = {
  find_handles: 'Find IG Handles',
  scrape_posts: 'Scrape IG Posts',
  extract_phones: 'Extract Phones',
  collect_universities: 'Collect Universities',
  discover_bem: 'Discover BEM',
  dms_research: 'Research Rektor',
}

const AGENT_COLORS: Record<PipelineAgentType, string> = {
  find_handles: 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300',
  scrape_posts: 'bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300',
  extract_phones: 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300',
  collect_universities: 'bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300',
  discover_bem: 'bg-teal-100 text-teal-700 dark:bg-teal-900/50 dark:text-teal-300',
  dms_research: 'bg-violet-100 text-violet-700 dark:bg-violet-900/50 dark:text-violet-300',
}

const STATUS_CONFIG: Record<PipelineLogStatus, { icon: typeof CheckCircle; color: string; label: string }> = {
  running: { icon: Loader2, color: 'text-blue-500', label: 'Running' },
  completed: { icon: CheckCircle, color: 'text-green-500', label: 'Completed' },
  failed: { icon: XCircle, color: 'text-red-500', label: 'Failed' },
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '-'
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return `${mins}m ${secs}s`
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString('id-ID', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    })
  } catch {
    return iso
  }
}

function LogDetailPanel({ log }: { log: PipelineLog }) {
  const summary = log.summary
  const details = log.details

  return (
    <div className="mt-3 space-y-3 border-t border-gray-200 pt-3 dark:border-gray-700">
      {/* Summary */}
      {summary && Object.keys(summary).length > 0 && (
        <div>
          <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Summary
          </h4>
          <div className="flex flex-wrap gap-2">
            {Object.entries(summary).map(([key, value]) => (
              <span
                key={key}
                className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-700 dark:bg-gray-700 dark:text-gray-300"
              >
                <span className="text-gray-500 dark:text-gray-400">{key.replace(/_/g, ' ')}:</span>
                <span className="font-semibold">{String(value ?? '-')}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Error */}
      {log.error && (
        <div className="rounded-md bg-red-50 p-3 dark:bg-red-900/20">
          <p className="text-sm text-red-700 dark:text-red-300">
            <span className="font-semibold">Error:</span> {log.error}
          </p>
        </div>
      )}

      {/* Details table */}
      {details && details.length > 0 && (
        <div>
          <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Details ({details.length} items)
          </h4>
          <div className="max-h-60 overflow-auto rounded-md border border-gray-200 dark:border-gray-700">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-gray-50 dark:bg-gray-800">
                <tr>
                  {Object.keys(details[0]).map((key) => (
                    <th key={key} className="px-3 py-1.5 font-medium text-gray-600 dark:text-gray-400">
                      {key.replace(/_/g, ' ')}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {details.map((item, idx) => (
                  <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                    {Object.values(item).map((val, vIdx) => (
                      <td key={vIdx} className="px-3 py-1.5 text-gray-700 dark:text-gray-300">
                        {typeof val === 'object' ? JSON.stringify(val) : String(val ?? '-')}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function LogRow({ log }: { log: PipelineLog }) {
  const [expanded, setExpanded] = useState(false)
  const statusCfg = STATUS_CONFIG[log.status]
  const StatusIcon = statusCfg.icon

  const hasDetails = (log.details && log.details.length > 0) || log.summary || log.error

  return (
    <div className="border-b border-gray-100 px-4 py-3 last:border-b-0 dark:border-gray-700/50">
      <div
        className={`flex items-center gap-3 ${hasDetails ? 'cursor-pointer' : ''}`}
        onClick={() => hasDetails && setExpanded(!expanded)}
      >
        {/* Status icon */}
        <StatusIcon
          className={`h-4 w-4 flex-shrink-0 ${statusCfg.color} ${log.status === 'running' ? 'animate-spin' : ''}`}
        />

        {/* Agent type badge */}
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${AGENT_COLORS[log.agent_type]}`}>
          {AGENT_LABELS[log.agent_type] || log.agent_type}
        </span>

        {/* Trigger type */}
        <span className={`rounded px-1.5 py-0.5 text-xs ${
          log.trigger_type === 'scheduler'
            ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300'
            : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
        }`}>
          {log.trigger_type === 'scheduler' ? '⏰ scheduler' : '👆 manual'}
        </span>

        {/* Counts */}
        <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
          {log.status !== 'running' && (
            <>
              <span className="font-medium text-gray-700 dark:text-gray-300">
                {log.items_processed} processed
              </span>
              {log.items_success > 0 && (
                <span className="font-medium text-green-600 dark:text-green-400">
                  ✓ {log.items_success}
                </span>
              )}
              {log.items_failed > 0 && (
                <span className="font-medium text-red-600 dark:text-red-400">
                  ✗ {log.items_failed}
                </span>
              )}
            </>
          )}
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Duration */}
        {log.duration_seconds != null && (
          <span className="flex items-center gap-1 text-xs text-gray-400 dark:text-gray-500">
            <Timer className="h-3 w-3" />
            {formatDuration(log.duration_seconds)}
          </span>
        )}

        {/* Time */}
        <span className="text-xs text-gray-400 dark:text-gray-500">
          {formatTime(log.started_at)}
        </span>

        {/* Expand chevron */}
        {hasDetails && (
          <div className="text-gray-400">
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </div>
        )}
      </div>

      {expanded && hasDetails && <LogDetailPanel log={log} />}
    </div>
  )
}

export function PipelineActivityLog() {
  const [filter, setFilter] = useState<string>('')
  const [page, setPage] = useState(0)
  const pageSize = 20

  const { data, isLoading } = usePipelineLogs({
    agent_type: filter || undefined,
    limit: pageSize,
    offset: page * pageSize,
  })

  const logs = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / pageSize)

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-gray-100 p-2 dark:bg-gray-800">
              <Clock className="h-5 w-5 text-gray-600 dark:text-gray-400" />
            </div>
            <div>
              <CardTitle>Activity Log</CardTitle>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {total} total runs
              </p>
            </div>
          </div>
          <select
            value={filter}
            onChange={(e) => { setFilter(e.target.value); setPage(0) }}
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
          >
            <option value="">All Agents</option>
            <option value="find_handles">Find IG Handles</option>
            <option value="scrape_posts">Scrape IG Posts</option>
            <option value="extract_phones">Extract Phones</option>
            <option value="collect_universities">Collect Universities</option>
            <option value="discover_bem">Discover BEM</option>
            <option value="dms_research">Research Rektor</option>
          </select>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
          </div>
        ) : logs.length === 0 ? (
          <div className="py-12 text-center text-sm text-gray-500 dark:text-gray-400">
            No pipeline runs yet. Trigger an agent above to get started.
          </div>
        ) : (
          <>
            <div className="divide-y divide-gray-100 dark:divide-gray-700/50">
              {logs.map((log) => (
                <LogRow key={log.id} log={log} />
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 dark:border-gray-700">
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  Page {page + 1} of {totalPages}
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => setPage(Math.max(0, page - 1))}
                    disabled={page === 0}
                    className="rounded px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-100 disabled:opacity-40 dark:text-gray-400 dark:hover:bg-gray-800"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
                    disabled={page >= totalPages - 1}
                    className="rounded px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-100 disabled:opacity-40 dark:text-gray-400 dark:hover:bg-gray-800"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
