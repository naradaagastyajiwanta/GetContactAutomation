import { Loader2, Search, Download, Phone, Clock, Users, GraduationCap } from 'lucide-react'
import { usePipelineStatus } from '../../hooks/usePipeline'
import { formatRelative } from '../../lib/utils'
import type { RunningAgent, PipelineAgentType } from '../../lib/types'

const AGENT_CONFIG: Record<PipelineAgentType, { label: string; icon: typeof Search; color: string; bgColor: string }> = {
  find_handles: {
    label: 'Find IG Handles',
    icon: Search,
    color: 'text-blue-700 dark:text-blue-300',
    bgColor: 'bg-blue-50 border-blue-200 dark:bg-blue-950/40 dark:border-blue-800',
  },
  scrape_posts: {
    label: 'Scrape IG Posts',
    icon: Download,
    color: 'text-purple-700 dark:text-purple-300',
    bgColor: 'bg-purple-50 border-purple-200 dark:bg-purple-950/40 dark:border-purple-800',
  },
  extract_phones: {
    label: 'Extract Phones',
    icon: Phone,
    color: 'text-emerald-700 dark:text-emerald-300',
    bgColor: 'bg-emerald-50 border-emerald-200 dark:bg-emerald-950/40 dark:border-emerald-800',
  },
  collect_universities: {
    label: 'Collect Universities',
    icon: Search,
    color: 'text-amber-700 dark:text-amber-300',
    bgColor: 'bg-amber-50 border-amber-200 dark:bg-amber-950/40 dark:border-amber-800',
  },
  discover_bem: {
    label: 'Discover BEM',
    icon: Users,
    color: 'text-teal-700 dark:text-teal-300',
    bgColor: 'bg-teal-50 border-teal-200 dark:bg-teal-950/40 dark:border-teal-800',
  },
  dms_research: {
    label: 'Research Rektor',
    icon: GraduationCap,
    color: 'text-violet-700 dark:text-violet-300',
    bgColor: 'bg-violet-50 border-violet-200 dark:bg-violet-950/40 dark:border-violet-800',
  },
}

function AgentPill({ agent }: { agent: RunningAgent }) {
  const cfg = AGENT_CONFIG[agent.agent_type] ?? AGENT_CONFIG.find_handles
  const Icon = cfg.icon

  return (
    <div className={`flex items-center gap-2.5 rounded-lg border px-3 py-2 ${cfg.bgColor}`}>
      {/* Pulsing dot */}
      <span className="relative flex h-2.5 w-2.5 shrink-0">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-75" />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-current" />
      </span>

      <Icon className={`h-4 w-4 shrink-0 ${cfg.color}`} />

      <div className="min-w-0 flex-1">
        <span className={`text-sm font-semibold ${cfg.color}`}>
          {cfg.label}
        </span>
        <div className={`flex items-center gap-2 text-xs opacity-80 ${cfg.color}`}>
          {agent.target_count != null && (
            <span>{agent.target_count} universit{agent.target_count === 1 ? 'y' : 'ies'}</span>
          )}
          {agent.items_processed > 0 && (
            <span>
              {agent.items_processed} processed
              {agent.items_success > 0 && ` (${agent.items_success} ok)`}
            </span>
          )}
          <span className="inline-flex items-center gap-0.5">
            <Clock className="h-3 w-3" />
            {formatRelative(agent.started_at)}
          </span>
        </div>
      </div>
    </div>
  )
}

/**
 * Banner shown on the Universities page when pipeline agents are currently running.
 * Polls /pipeline/status every 5s to get running agents list.
 */
export function RunningAgentsBanner() {
  const { data: status } = usePipelineStatus()
  const running = status?.running_agents ?? []

  if (running.length === 0) return null

  return (
    <div className="rounded-lg border border-indigo-200 bg-indigo-50/60 p-3 dark:border-indigo-800 dark:bg-indigo-950/30">
      <div className="mb-2 flex items-center gap-2">
        <Loader2 className="h-4 w-4 animate-spin text-indigo-600 dark:text-indigo-400" />
        <span className="text-sm font-semibold text-indigo-700 dark:text-indigo-300">
          {running.length} agent{running.length > 1 ? 's' : ''} running
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        {running.map((agent) => (
          <AgentPill key={agent.id} agent={agent} />
        ))}
      </div>
    </div>
  )
}
