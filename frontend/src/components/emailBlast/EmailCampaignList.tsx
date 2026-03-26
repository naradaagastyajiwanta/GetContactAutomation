/**
 * EmailCampaignList — Campaign list with Gmail-style rows.
 */

import { useState } from 'react'
import {
  Plus,
  FileText,
  Rocket,
  Pause,
  CheckCircle2,
  XCircle,
  Search,
  Send,
  ChevronRight,
  MoreHorizontal,
  TrendingUp,
  Users,
} from 'lucide-react'
import { cn, formatDate } from '../../lib/utils'
import { Button } from '../ui/Button'
import { EmptyState } from '../ui/EmptyState'
import type { EmailBlastCampaign } from '../../api/emailBlast'

interface CampaignCounts {
  draft: number
  running: number
  paused: number
  completed: number
  cancelled: number
}

interface Props {
  campaigns: EmailBlastCampaign[]
  campaignCounts: CampaignCounts
  onSelect: (campaign: EmailBlastCampaign) => void
  onNew: () => void
  statusFilter: string
  onStatusChange: (status: string) => void
}

const statusConfig: Record<
  string,
  { label: string; icon: React.ElementType; color: string; bg: string }
> = {
  draft: {
    label: 'Draft',
    icon: FileText,
    color: 'text-gray-500',
    bg: 'bg-gray-100 text-gray-600',
  },
  running: {
    label: 'Active',
    icon: Rocket,
    color: 'text-blue-600',
    bg: 'bg-blue-100 text-blue-700',
  },
  paused: {
    label: 'Paused',
    icon: Pause,
    color: 'text-amber-600',
    bg: 'bg-amber-100 text-amber-700',
  },
  completed: {
    label: 'Done',
    icon: CheckCircle2,
    color: 'text-green-600',
    bg: 'bg-green-100 text-green-700',
  },
  cancelled: {
    label: 'Cancelled',
    icon: XCircle,
    color: 'text-red-600',
    bg: 'bg-red-100 text-red-700',
  },
}

function ProgressBar({
  sent,
  failed,
  total,
}: {
  sent: number
  failed: number
  total: number
}) {
  if (total === 0) return null
  const sentPct = (sent / total) * 100
  const failedPct = (failed / total) * 100

  return (
    <div className="w-32">
      <div className="h-1.5 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700">
        <div className="flex h-full">
          {sentPct > 0 && (
            <div
              className="bg-green-400 transition-all duration-500"
              style={{ width: `${sentPct}%` }}
            />
          )}
          {failedPct > 0 && (
            <div
              className="bg-red-400 transition-all duration-500"
              style={{ width: `${failedPct}%` }}
            />
          )}
          {sentPct === 0 && failedPct === 0 && (
            <div className="h-full w-full bg-gray-200 dark:bg-gray-600" />
          )}
        </div>
      </div>
      <div className="mt-1 text-[10px] text-gray-400">
        {sent + failed}/{total}
      </div>
    </div>
  )
}

function CampaignRow({
  campaign,
  onClick,
}: {
  campaign: EmailBlastCampaign
  onClick: () => void
}) {
  const cfg = statusConfig[campaign.status] ?? statusConfig.draft
  const Icon = cfg.icon

  return (
    <div
      onClick={onClick}
      className="group flex cursor-pointer items-center gap-4 border-b border-gray-50 px-4 py-3.5 transition-colors hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/50"
    >
      {/* Icon */}
      <div
        className={cn(
          'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl',
          campaign.status === 'running'
            ? 'bg-blue-100 dark:bg-blue-900/40'
            : campaign.status === 'completed'
            ? 'bg-green-100 dark:bg-green-900/40'
            : campaign.status === 'paused'
            ? 'bg-amber-100 dark:bg-amber-900/40'
            : campaign.status === 'cancelled'
            ? 'bg-red-100 dark:bg-red-900/40'
            : 'bg-gray-100 dark:bg-gray-800',
        )}
      >
        <Icon
          className={cn(
            'h-5 w-5',
            campaign.status === 'running'
              ? 'text-blue-600 dark:text-blue-400'
              : campaign.status === 'completed'
              ? 'text-green-600 dark:text-green-400'
              : campaign.status === 'paused'
              ? 'text-amber-600 dark:text-amber-400'
              : campaign.status === 'cancelled'
              ? 'text-red-600 dark:text-red-400'
              : 'text-gray-400 dark:text-gray-500',
          )}
        />
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-[13px] font-semibold text-gray-900 dark:text-gray-100">
            {campaign.name || '(Untitled Campaign)'}
          </span>
          <span
            className={cn(
              'shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium',
              cfg.bg,
            )}
          >
            {cfg.label}
          </span>
        </div>
        <div className="mt-0.5 flex items-center gap-3 text-[11px] text-gray-400">
          <span className="flex items-center gap-1">
            <Users className="h-3 w-3" />
            {campaign.total_recipients} recipients
          </span>
          <span>{formatDate(campaign.created_at)}</span>
        </div>
      </div>

      {/* Progress */}
      <div className="shrink-0">
        <ProgressBar
          sent={campaign.sent_count}
          failed={campaign.failed_count}
          total={campaign.total_recipients}
        />
      </div>

      {/* Arrow */}
      <ChevronRight className="h-4 w-4 shrink-0 text-gray-300 opacity-0 transition-opacity group-hover:opacity-100 dark:text-gray-600" />
    </div>
  )
}

export function EmailCampaignList({
  campaigns,
  campaignCounts,
  onSelect,
  onNew,
  statusFilter,
  onStatusChange,
}: Props) {
  const [search, setSearch] = useState('')

  const filtered = campaigns.filter((c) => {
    const matchStatus = !statusFilter || c.status === statusFilter
    const matchSearch =
      !search.trim() ||
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.subject.toLowerCase().includes(search.toLowerCase())
    return matchStatus && matchSearch
  })

  const statusTabs = [
    { key: '', label: 'All', count: campaigns.length },
    { key: 'draft', label: 'Draft', count: campaignCounts.draft },
    { key: 'running', label: 'Active', count: campaignCounts.running },
    { key: 'paused', label: 'Paused', count: campaignCounts.paused },
    { key: 'completed', label: 'Done', count: campaignCounts.completed },
    { key: 'cancelled', label: 'Cancelled', count: campaignCounts.cancelled },
  ]

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Top bar */}
      <div className="flex items-center gap-3 border-b border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-[#111827]">
        <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
          <FileText className="h-4 w-4" />
          <span>Campaigns</span>
          <span className="text-xs">({filtered.length})</span>
        </div>

        <div className="ml-auto flex items-center gap-2">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search campaigns..."
              className="h-8 w-48 rounded-lg border border-gray-200 bg-gray-50 pl-8 pr-3 text-xs text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
            />
          </div>

          <Button size="sm" onClick={onNew}>
            <Plus className="h-3.5 w-3.5" />
            New
          </Button>
        </div>
      </div>

      {/* Status tabs */}
      <div className="flex gap-1 border-b border-gray-200 bg-white px-4 py-2 dark:border-gray-800 dark:bg-[#111827]">
        {statusTabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => onStatusChange(tab.key)}
            className={cn(
              'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors',
              statusFilter === tab.key
                ? 'bg-gray-900 text-white dark:bg-indigo-600 dark:text-white'
                : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200',
            )}
          >
            {tab.label}
            {tab.count > 0 && (
              <span
                className={cn(
                  'flex h-4 min-w-[16px] items-center justify-center rounded-full px-1 text-[10px]',
                  statusFilter === tab.key
                    ? 'bg-white/20 text-white'
                    : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
                )}
              >
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto bg-white dark:bg-[#111827]">
        {filtered.length === 0 ? (
          <EmptyState
            icon={FileText}
            title={search ? 'No campaigns match your search' : 'No campaigns yet'}
            description={
              search
                ? 'Try a different search term.'
                : 'Create your first email campaign to get started.'
            }
            action={
              !search ? (
                <Button onClick={onNew}>
                  <Plus className="h-4 w-4" />
                  New Campaign
                </Button>
              ) : undefined
            }
          />
        ) : (
          <div>
            {filtered.map((campaign) => (
              <CampaignRow
                key={campaign.id}
                campaign={campaign}
                onClick={() => onSelect(campaign)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
