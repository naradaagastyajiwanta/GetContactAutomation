/**
 * BlastCampaignsPage — List all blast campaigns with status, progress, and quick actions.
 */

import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Megaphone,
  Plus,
  Play,
  Pause,
  Trash2,
  XCircle,
  Clock,
  CheckCircle2,
  Send,
  CalendarClock,
  Loader2,
  ChevronRight,
  Sparkles,
  RotateCw,
} from 'lucide-react'
import { cn } from '../lib/utils'
import {
  useBlastCampaigns,
  useCreateCampaign,
  useDeleteCampaign,
  useStartCampaign,
  usePauseCampaign,
  useCancelCampaign,
} from '../hooks/useBlast'
import { useAuth } from '../context/AuthContext'
import type { BlastCampaign } from '../api/blast'

const statusConfig: Record<
  string,
  { label: string; color: string; bg: string; icon: React.ElementType }
> = {
  draft: { label: 'Draft', color: 'text-gray-600 dark:text-gray-400', bg: 'bg-gray-100 dark:bg-gray-800', icon: Clock },
  sending: { label: 'Sending', color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-900/30', icon: Send },
  paused: { label: 'Paused', color: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-50 dark:bg-amber-900/30', icon: Pause },
  completed: { label: 'Completed', color: 'text-green-600 dark:text-green-400', bg: 'bg-green-50 dark:bg-green-900/30', icon: CheckCircle2 },
  cancelled: { label: 'Cancelled', color: 'text-red-600 dark:text-red-400', bg: 'bg-red-50 dark:bg-red-900/30', icon: XCircle },
}

function StatusBadge({ status }: { status: string }) {
  const cfg = statusConfig[status] || statusConfig.draft
  const Icon = cfg.icon
  return (
    <span className={cn('inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold', cfg.bg, cfg.color)}>
      <Icon className="w-3 h-3" />
      {cfg.label}
    </span>
  )
}

function ProgressBar({ sent, failed, total }: { sent: number; failed: number; total: number }) {
  if (total === 0) return null
  const sentPct = (sent / total) * 100
  const failedPct = (failed / total) * 100

  return (
    <div className="w-full">
      <div className="flex items-center justify-between text-[11px] text-gray-500 dark:text-gray-400 mb-1">
        <span>{sent + failed}/{total}</span>
        <span>{Math.round(sentPct + failedPct)}%</span>
      </div>
      <div className="h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden flex">
        {sentPct > 0 && (
          <div className="bg-green-500 h-full transition-all duration-500" style={{ width: `${sentPct}%` }} />
        )}
        {failedPct > 0 && (
          <div className="bg-red-400 h-full transition-all duration-500" style={{ width: `${failedPct}%` }} />
        )}
      </div>
    </div>
  )
}

function SafetyBadge({
  icon: Icon,
  label,
  tone,
}: {
  icon: React.ElementType
  label: string
  tone: 'blue' | 'violet' | 'emerald'
}) {
  const tones = {
    blue: 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 border-blue-200 dark:border-blue-800',
    violet: 'bg-violet-50 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300 border-violet-200 dark:border-violet-800',
    emerald: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800',
  }

  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium', tones[tone])}>
      <Icon className="h-3 w-3" />
      {label}
    </span>
  )
}

function formatRelativeCountdown(target: string | null, now: number): string | null {
  if (!target) return null
  const targetMs = new Date(target).getTime()
  if (!Number.isFinite(targetMs)) return null
  const diffMs = targetMs - now
  if (diffMs <= 0) return 'resuming now'

  const totalSeconds = Math.ceil(diffMs / 1000)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  if (hours > 0) return `auto-resume in ${hours}h ${minutes}m`
  if (minutes > 0) return `auto-resume in ${minutes}m ${seconds}s`
  return `auto-resume in ${seconds}s`
}

export default function BlastCampaignsPage() {
  const { hasPermission } = useAuth()
  const navigate = useNavigate()
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(interval)
  }, [])

  const { data, isLoading } = useBlastCampaigns()
  const createMutation = useCreateCampaign()
  const deleteMutation = useDeleteCampaign()
  const startMutation = useStartCampaign()
  const pauseMutation = usePauseCampaign()
  const cancelMutation = useCancelCampaign()
  const canManageBlast = hasPermission('blast.manage')

  const campaigns = data?.data || []

  const handleCreate = () => {
    if (!newName.trim()) return
    createMutation.mutate(
      { name: newName.trim() },
      {
        onSuccess: (result) => {
          setNewName('')
          setShowCreate(false)
          if (result.success && result.campaign) {
            navigate(`/blast/${result.campaign.id}`)
          }
        },
      }
    )
  }

  return (
    <div className="max-w-5xl mx-auto py-6 px-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 text-white shadow-lg">
            <Megaphone className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">WA Blast</h1>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Create campaigns, select contacts, send templated messages
            </p>
          </div>
        </div>
        {canManageBlast && (
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg shadow-sm transition-colors"
          >
            <Plus className="w-4 h-4" />
            New Campaign
          </button>
        )}
      </div>

      {/* Create Campaign Inline */}
      {canManageBlast && showCreate && (
        <div className="mb-5 p-4 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Create New Campaign</h3>
          <div className="flex gap-2">
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              placeholder="Campaign name, e.g. 'Blast Universitas Jawa Barat'"
              autoFocus
              className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-900 dark:text-gray-100"
            />
            <button
              onClick={handleCreate}
              disabled={createMutation.isPending || !newName.trim()}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg disabled:opacity-50 transition-colors"
            >
              {createMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Create'}
            </button>
            <button
              onClick={() => { setShowCreate(false); setNewName('') }}
              className="px-3 py-2 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Campaign List */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
        </div>
      ) : campaigns.length === 0 ? (
        <div className="text-center py-20">
          <Megaphone className="w-12 h-12 mx-auto text-gray-300 dark:text-gray-600 mb-3" />
          <p className="text-gray-500 dark:text-gray-400 text-sm">No campaigns yet.</p>
          <p className="text-gray-400 dark:text-gray-500 text-xs mt-1">
            Create your first campaign to start blasting.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {campaigns.map((c) => (
            <CampaignCard
              key={c.id}
              campaign={c}
              now={now}
              canManage={canManageBlast}
              onStart={() => startMutation.mutate(c.id)}
              onPause={() => pauseMutation.mutate(c.id)}
              onCancel={() => cancelMutation.mutate(c.id)}
              onDelete={() => {
                if (confirm('Delete this campaign?')) deleteMutation.mutate(c.id)
              }}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function CampaignCard({
  campaign: c,
  now,
  canManage,
  onStart,
  onPause,
  onCancel,
  onDelete,
}: {
  campaign: BlastCampaign
  now: number
  canManage: boolean
  onStart: () => void
  onPause: () => void
  onCancel: () => void
  onDelete: () => void
}) {
  const resumeLabel = formatRelativeCountdown(c.auto_resume_at, now)

  return (
    <Link
      to={`/blast/${c.id}`}
      className="block bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 hover:border-indigo-300 dark:hover:border-indigo-600 transition-all shadow-sm hover:shadow-md group"
    >
      <div className="flex items-start justify-between gap-4">
        {/* Left: Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
              {c.name}
            </h3>
            <StatusBadge status={c.status} />
          </div>

          <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-1 mb-2">
            {c.template_message
              ? c.template_message.substring(0, 120) + (c.template_message.length > 120 ? '...' : '')
              : 'No template set'}
          </p>

          {/* Stats row */}
          <div className="flex items-center gap-4 text-[11px] text-gray-500 dark:text-gray-400">
            <span>{c.total_recipients} recipients</span>
            {c.sent_count > 0 && <span className="text-green-600 dark:text-green-400">{c.sent_count} sent</span>}
            {c.failed_count > 0 && <span className="text-red-500">{c.failed_count} failed</span>}
            <span>{c.device_id}</span>
            <span>{new Date(c.created_at).toLocaleDateString()}</span>
          </div>

          <div className="mt-2 flex flex-wrap gap-1.5">
            {Boolean(c.schedule_enabled) && (
              <SafetyBadge icon={CalendarClock} label="Scheduler on" tone="blue" />
            )}
            {Boolean(c.content_variation_enabled) && (
              <SafetyBadge icon={Sparkles} label="Variation on" tone="violet" />
            )}
            {Boolean(c.auto_resume_enabled) && (
              <SafetyBadge icon={RotateCw} label="Auto-resume on" tone="emerald" />
            )}
          </div>

          {c.status === 'paused' && (c.paused_reason || resumeLabel) && (
            <div className="mt-2 space-y-1">
              {c.paused_reason && (
                <p className="text-[11px] text-amber-700 dark:text-amber-300 line-clamp-2">
                  Paused: {c.paused_reason}
                </p>
              )}
              {resumeLabel && Boolean(c.auto_resume_enabled) && (
                <p className="text-[11px] text-blue-600 dark:text-blue-400">
                  {resumeLabel}
                </p>
              )}
            </div>
          )}

          {/* Progress bar for active campaigns */}
          {(c.status === 'sending' || c.status === 'paused' || c.status === 'completed') &&
            c.total_recipients > 0 && (
              <div className="mt-2 max-w-xs">
                <ProgressBar sent={c.sent_count} failed={c.failed_count} total={c.total_recipients} />
              </div>
            )}
        </div>

        {/* Right: Actions */}
        {canManage && (
          <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.preventDefault()}>
            {c.status === 'draft' && c.total_recipients > 0 && (
              <button
                onClick={onStart}
                className="p-1.5 rounded-lg text-green-600 hover:bg-green-50 dark:hover:bg-green-900/30 transition-colors"
                title="Start"
              >
                <Play className="w-4 h-4" />
              </button>
            )}
            {c.status === 'paused' && (
              <button
                onClick={onStart}
                className="p-1.5 rounded-lg text-green-600 hover:bg-green-50 dark:hover:bg-green-900/30 transition-colors"
                title="Resume"
              >
                <Play className="w-4 h-4" />
              </button>
            )}
            {c.status === 'sending' && (
              <button
                onClick={onPause}
                className="p-1.5 rounded-lg text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-900/30 transition-colors"
                title="Pause"
              >
                <Pause className="w-4 h-4" />
              </button>
            )}
            {(c.status === 'sending' || c.status === 'paused') && (
              <button
                onClick={onCancel}
                className="p-1.5 rounded-lg text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors"
                title="Cancel"
              >
                <XCircle className="w-4 h-4" />
              </button>
            )}
            {(c.status === 'draft' || c.status === 'completed' || c.status === 'cancelled') && (
              <button
                onClick={onDelete}
                className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors"
                title="Delete"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            )}
            <ChevronRight className="w-4 h-4 text-gray-300 dark:text-gray-600 group-hover:text-indigo-400 transition-colors ml-1" />
          </div>
        )}
      </div>
    </Link>
  )
}
