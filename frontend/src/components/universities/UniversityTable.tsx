import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Play, Search, Download, Phone, Users, ChevronDown, AlertTriangle } from 'lucide-react'
import toast from 'react-hot-toast'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../ui/Table'
import { Badge } from '../ui/Badge'
import { STATUS_COLORS } from '../../lib/constants'
import { formatDate } from '../../lib/utils'
import { useToggleEnabled, useBulkToggle } from '../../hooks/useUniversities'
import { useRunAgentTargeted } from '../../hooks/usePipeline'
import { useHealth } from '../../hooks/useHealth'
import type { University } from '../../lib/types'
import type { TargetedAgentType } from '../../api/pipeline'

/** Agents that require a valid IG session */
const IG_DEPENDENT_AGENTS: Set<TargetedAgentType> = new Set(['find_handles', 'scrape_posts', 'discover_bem'])

const AGENT_OPTIONS: { value: TargetedAgentType; label: string; icon: typeof Search; description: string }[] = [
  { value: 'find_handles', label: 'Find IG Handle', icon: Search, description: 'Search Instagram handle' },
  { value: 'discover_bem', label: 'Discover BEM', icon: Users, description: 'Find BEM & scan following' },
  { value: 'scrape_posts', label: 'Scrape IG Posts', icon: Download, description: 'Scrape Instagram posts' },
  { value: 'extract_phones', label: 'Extract Phones', icon: Phone, description: 'Extract phone numbers from posts' },
]

interface UniversityTableProps {
  universities: University[]
  selected: Set<number>
  onSelectedChange: (selected: Set<number>) => void
}

function RowAgentMenu({ uniId, status, onRunAgent, isPending, igDown }: {
  uniId: number
  status: string
  onRunAgent: (agentType: TargetedAgentType, uniId: number) => void
  isPending: boolean
  igDown?: boolean
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    if (open) document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  // Suggest the most relevant agent based on current status
  const suggestedAgent: TargetedAgentType | null =
    status === 'pending' ? 'find_handles' :
    status === 'ig_found' ? 'scrape_posts' :
    status === 'ig_scraped' ? 'extract_phones' :
    null

  return (
    <div className="relative inline-block" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        disabled={isPending}
        className="inline-flex items-center gap-0.5 rounded px-1.5 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-50 dark:text-gray-400 dark:hover:bg-gray-700"
        title="Run agent"
      >
        <Play className="h-3.5 w-3.5" />
        <ChevronDown className="h-3 w-3" />
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-1 w-48 rounded-lg border border-gray-200 bg-white py-1 shadow-lg dark:border-gray-600 dark:bg-gray-800">
          {igDown && (
            <div className="flex items-center gap-1.5 border-b border-gray-100 px-3 py-1.5 dark:border-gray-700">
              <AlertTriangle className="h-3 w-3 text-amber-500" />
              <span className="text-[10px] text-amber-600 dark:text-amber-400">IG session expired</span>
            </div>
          )}
          {AGENT_OPTIONS.map(({ value, label, icon: Icon }) => (
            <button
              key={value}
              onClick={() => { onRunAgent(value, uniId); setOpen(false) }}
              disabled={isPending}
              className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-gray-100 disabled:opacity-50 dark:hover:bg-gray-700 ${
                value === suggestedAgent
                  ? 'font-medium text-indigo-700 dark:text-indigo-300'
                  : 'text-gray-700 dark:text-gray-200'
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
              {value === suggestedAgent && (
                <span className="ml-auto text-[10px] text-indigo-500 dark:text-indigo-400">suggested</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export function UniversityTable({ universities, selected, onSelectedChange }: UniversityTableProps) {
  const navigate = useNavigate()
  const toggleMutation = useToggleEnabled()
  const bulkMutation = useBulkToggle()
  const agentMutation = useRunAgentTargeted()
  const { data: health } = useHealth()
  const igSessionOk = health?.instagram?.ok ?? true
  const [bulkAgentOpen, setBulkAgentOpen] = useState(false)
  const bulkAgentRef = useRef<HTMLDivElement>(null)
  const selectAllRef = useRef<HTMLInputElement>(null)

  const allIds = universities.map((u) => u.id)
  const allSelected = universities.length > 0 && allIds.every((id) => selected.has(id))
  const someSelected = universities.length > 0 && !allSelected && allIds.some((id) => selected.has(id))

  // Set indeterminate state on "select all" checkbox
  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = someSelected
    }
  }, [someSelected])

  const toggleSelect = (id: number) => {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    onSelectedChange(next)
  }

  const toggleAll = () => {
    const next = new Set(selected)
    if (allSelected) {
      // Remove only current page items
      allIds.forEach((id) => next.delete(id))
    } else {
      // Add current page items (preserving other pages)
      allIds.forEach((id) => next.add(id))
    }
    onSelectedChange(next)
  }

  const handleBulk = (enabled: boolean) => {
    bulkMutation.mutate({ ids: Array.from(selected), enabled }, {
      onSuccess: () => onSelectedChange(new Set()),
    })
  }

  /** Warn user if IG session is expired, but still allow them to proceed */
  const warnIfIgDown = (agentType: TargetedAgentType): boolean => {
    if (!igSessionOk && IG_DEPENDENT_AGENTS.has(agentType)) {
      toast(
        'IG session is expired — this agent may return empty results. Update session ID in Settings.',
        { icon: '⚠️', duration: 5000 }
      )
    }
    return true
  }

  const handleBulkAgent = (agentType: TargetedAgentType) => {
    warnIfIgDown(agentType)
    agentMutation.mutate(
      { agentType, universityIds: Array.from(selected) },
      { onSuccess: () => { onSelectedChange(new Set()); setBulkAgentOpen(false) } },
    )
  }

  const handleSingleAgent = (agentType: TargetedAgentType, uniId: number) => {
    warnIfIgDown(agentType)
    agentMutation.mutate({ agentType, universityIds: [uniId] })
  }

  // Close bulk agent dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (bulkAgentRef.current && !bulkAgentRef.current.contains(e.target as Node)) {
        setBulkAgentOpen(false)
      }
    }
    if (bulkAgentOpen) document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [bulkAgentOpen])

  return (
    <div>
      {selected.size > 0 && (
        <div className="flex items-center gap-3 border-b border-gray-200 bg-indigo-50 px-4 py-2 dark:border-gray-700 dark:bg-indigo-950/30">
          <span className="text-sm font-medium text-indigo-700 dark:text-indigo-300">
            {selected.size} selected
          </span>
          <button
            onClick={() => handleBulk(true)}
            disabled={bulkMutation.isPending}
            className="rounded bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            Enable Selected
          </button>
          <button
            onClick={() => handleBulk(false)}
            disabled={bulkMutation.isPending}
            className="rounded bg-red-600 px-3 py-1 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
          >
            Disable Selected
          </button>

          {/* Run Agent dropdown */}
          <div className="relative" ref={bulkAgentRef}>
            <button
              onClick={() => setBulkAgentOpen(!bulkAgentOpen)}
              disabled={agentMutation.isPending}
              className="inline-flex items-center gap-1 rounded bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              <Play className="h-3 w-3" />
              Run Agent
              <ChevronDown className="h-3 w-3" />
            </button>
            {bulkAgentOpen && (
              <div className="absolute left-0 z-50 mt-1 w-52 rounded-lg border border-gray-200 bg-white py-1 shadow-lg dark:border-gray-600 dark:bg-gray-800">
                {AGENT_OPTIONS.map(({ value, label, icon: Icon, description }) => (
                  <button
                    key={value}
                    onClick={() => handleBulkAgent(value)}
                    disabled={agentMutation.isPending}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:text-gray-200 dark:hover:bg-gray-700"
                  >
                    <Icon className="h-4 w-4 text-gray-500 dark:text-gray-400" />
                    <div>
                      <div className="font-medium">{label}</div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">{description}</div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={() => onSelectedChange(new Set())}
            className="text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          >
            Clear
          </button>
        </div>
      )}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-10">
              <input
                ref={selectAllRef}
                type="checkbox"
                checked={allSelected}
                onChange={toggleAll}
                className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              />
            </TableHead>
            <TableHead>Name</TableHead>
            <TableHead>Province</TableHead>
            <TableHead className="text-right">Mahasiswa</TableHead>
            <TableHead>IG Handle</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="w-28 text-center">Contacts</TableHead>
            <TableHead className="w-24 text-center">Enabled</TableHead>
            <TableHead>Updated</TableHead>
            <TableHead className="w-20 text-center">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {universities.map((uni) => {
            const colors = STATUS_COLORS[uni.status] || STATUS_COLORS.pending
            const isEnabled = uni.enabled !== false && uni.enabled !== 0
            return (
              <TableRow
                key={uni.id}
                className={`cursor-pointer ${!isEnabled ? 'opacity-50' : ''}`}
              >
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={selected.has(uni.id)}
                    onChange={() => toggleSelect(uni.id)}
                    className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  />
                </TableCell>
                <TableCell>
                  <button
                    className="text-left font-medium text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
                    onClick={() => navigate(`/universities/${uni.id}`)}
                  >
                    {uni.name}
                  </button>
                </TableCell>
                <TableCell>{uni.province || '-'}</TableCell>
                <TableCell className="text-right">
                  {uni.student_count ? (
                    <span className="font-mono text-sm text-gray-600 dark:text-gray-400">
                      {uni.student_count.toLocaleString('id-ID')}
                    </span>
                  ) : (
                    <span className="text-xs text-gray-400">—</span>
                  )}
                </TableCell>
                <TableCell>
                  {uni.ig_handle ? (
                    <span className="text-gray-700 dark:text-gray-300">@{uni.ig_handle}</span>
                  ) : (
                    '-'
                  )}
                </TableCell>
                <TableCell>
                  <span className="inline-flex items-center gap-1">
                    <Badge className={`${colors.bg} ${colors.text}`}>
                      {uni.status}
                    </Badge>
                    {uni.status === 'bem_discovered' && uni.bem_discovery_status !== 'discovered' && (
                      <span
                        title={`BEM belum ditemukan (${uni.bem_discovery_attempts ?? 0}/3 percobaan)`}
                        className="text-amber-500 dark:text-amber-400"
                      >
                        <AlertTriangle className="h-3.5 w-3.5" />
                      </span>
                    )}
                  </span>
                </TableCell>
                <TableCell className="text-center">
                  {(uni.total_contacts ?? 0) === 0 ? (
                    <span className="text-xs text-gray-400">—</span>
                  ) : (
                    <span className="inline-flex items-center gap-1">
                      <span className={`text-sm font-semibold ${
                        (uni.contacted_contacts ?? 0) > 0
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : 'text-gray-400'
                      }`}>
                        {uni.contacted_contacts ?? 0}
                      </span>
                      <span className="text-xs text-gray-400">/ {uni.total_contacts}</span>
                    </span>
                  )}
                </TableCell>
                <TableCell className="text-center" onClick={(e) => e.stopPropagation()}>
                  <button
                    onClick={() =>
                      toggleMutation.mutate({ id: uni.id, enabled: !isEnabled })
                    }
                    disabled={toggleMutation.isPending}
                    className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50 ${
                      isEnabled ? 'bg-emerald-500' : 'bg-gray-300 dark:bg-gray-600'
                    }`}
                    title={isEnabled ? 'Click to disable' : 'Click to enable'}
                  >
                    <span
                      className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                        isEnabled ? 'translate-x-4' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </TableCell>
                <TableCell>{formatDate(uni.updated_at || uni.created_at)}</TableCell>
                <TableCell className="text-center" onClick={(e) => e.stopPropagation()}>
                  <RowAgentMenu
                    uniId={uni.id}
                    status={uni.status}
                    onRunAgent={handleSingleAgent}
                    isPending={agentMutation.isPending}
                    igDown={!igSessionOk}
                  />
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
