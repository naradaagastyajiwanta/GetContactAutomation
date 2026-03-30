import { useState, useMemo } from 'react'
import { CalendarClock, RefreshCw, Search, GraduationCap } from 'lucide-react'
import { useDmsStats, useDmsSchedules, useDmsFollowups, useTriggerScheduleSync, useDmsResearchResults } from '../hooks/useDms'
import { triggerResearchForSchedule } from '../api/dms'
import { DmsStatsCards } from '../components/dms/DmsStatsCards'
import { DmsScheduleTable } from '../components/dms/DmsScheduleTable'
import type { ScheduleSortKey, SortDir } from '../components/dms/DmsScheduleTable'
import { DmsFollowupTimeline } from '../components/dms/DmsFollowupTimeline'
import { Card } from '../components/ui/Card'
import { Spinner } from '../components/ui/Spinner'
import { Pagination } from '../components/ui/Pagination'
import { cn } from '../lib/utils'

type Tab = 'upcoming' | 'past' | 'followups'

const ITEMS_PER_PAGE = 25

export default function DmsSchedulesPage() {
  const [tab, setTab] = useState<Tab>('upcoming')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [sortKey, setSortKey] = useState<ScheduleSortKey | null>('jadwal_audiensi')
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  // Data hooks
  const { data: stats, isLoading: statsLoading } = useDmsStats()
  const { data: schedulesData, isLoading: schedulesLoading } = useDmsSchedules(365, 365)
  const { data: followupsData, isLoading: followupsLoading } = useDmsFollowups(100)
  const syncMutation = useTriggerScheduleSync()
  const { data: researchData } = useDmsResearchResults()
  const [researchProgress, setResearchProgress] = useState<{
    running: boolean
    done: number
    total: number
  } | null>(null)

  const allSchedules = schedulesData?.schedules ?? []
  const allFollowups = followupsData?.followups ?? []

  // Split schedules into upcoming / past
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  const { upcoming, past } = useMemo(() => {
    const up: typeof allSchedules = []
    const pa: typeof allSchedules = []
    for (const s of allSchedules) {
      if (!s.jadwal_audiensi) {
        up.push(s)
        continue
      }
      const d = new Date(s.jadwal_audiensi)
      if (d >= today) up.push(s)
      else pa.push(s)
    }
    return { upcoming: up, past: pa.reverse() }
  }, [allSchedules])

  const researchedIds = useMemo(() => {
    const ids = new Set<number>()
    for (const r of researchData?.results ?? []) ids.add(r.schedule_id)
    return ids
  }, [researchData])

  const unresearchedUpcoming = useMemo(
    () => upcoming.filter((s) => !researchedIds.has(s.id)),
    [upcoming, researchedIds],
  )

  // Apply search filter & sorting
  const filtered = useMemo(() => {
    const source = tab === 'upcoming' ? upcoming : tab === 'past' ? past : []
    let result = source
    if (search.trim()) {
      const q = search.toLowerCase()
      result = source.filter(
        (s) =>
          (s.nama_universitas ?? '').toLowerCase().includes(q) ||
          (s.alamat ?? '').toLowerCase().includes(q) ||
          (s.catatan ?? '').toLowerCase().includes(q),
      )
    }
    if (sortKey) {
      const dir = sortDir === 'asc' ? 1 : -1
      result = [...result].sort((a, b) => {
        const av = a[sortKey]
        const bv = b[sortKey]
        if (av == null && bv == null) return 0
        if (av == null) return 1
        if (bv == null) return -1
        if (typeof av === 'string' && typeof bv === 'string') {
          return av.localeCompare(bv, 'id') * dir
        }
        return (av < bv ? -1 : av > bv ? 1 : 0) * dir
      })
    }
    return result
  }, [tab, upcoming, past, search, sortKey, sortDir])

  // Pagination
  const totalPages = Math.max(1, Math.ceil(filtered.length / ITEMS_PER_PAGE))
  const paged = filtered.slice((page - 1) * ITEMS_PER_PAGE, page * ITEMS_PER_PAGE)

  const handleTabChange = (t: Tab) => {
    setTab(t)
    setPage(1)
  }

  const handleSearchChange = (v: string) => {
    setSearch(v)
    setPage(1)
  }

  const handleSort = (key: ScheduleSortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
    setPage(1)
  }

  const handleBulkResearch = async () => {
    if (researchProgress?.running) return
    const targets = unresearchedUpcoming
    if (targets.length === 0) return
    setResearchProgress({ running: true, done: 0, total: targets.length })
    for (let i = 0; i < targets.length; i++) {
      try {
        await triggerResearchForSchedule(targets[i].id, targets[i].source)
      } catch {
        // ignore individual errors, continue to next
      }
      setResearchProgress({ running: true, done: i + 1, total: targets.length })
      if (i < targets.length - 1) await new Promise((r) => setTimeout(r, 300))
    }
    setResearchProgress({ running: false, done: targets.length, total: targets.length })
    setTimeout(() => setResearchProgress(null), 4000)
  }

  const isLoading = tab === 'followups' ? followupsLoading : schedulesLoading

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <CalendarClock className="h-7 w-7 text-indigo-600 dark:text-indigo-400" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            DMS Audiensi Schedules
          </h1>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleBulkResearch}
            disabled={researchProgress?.running || unresearchedUpcoming.length === 0}
            className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-purple-700 disabled:opacity-50 dark:bg-purple-500 dark:hover:bg-purple-600"
          >
            <GraduationCap
              className={cn('h-4 w-4', researchProgress?.running && 'animate-pulse')}
            />
            {researchProgress
              ? researchProgress.running
                ? `Researching ${researchProgress.done}/${researchProgress.total}...`
                : `✓ Done (${researchProgress.done} triggered)`
              : `Research Rektor (${unresearchedUpcoming.length} belum)`}
          </button>

          <button
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
            className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-50 dark:bg-indigo-500 dark:hover:bg-indigo-600"
          >
            <RefreshCw className={cn('h-4 w-4', syncMutation.isPending && 'animate-spin')} />
            {syncMutation.isPending ? 'Syncing...' : 'Sync Now'}
          </button>
        </div>
      </div>

      {/* Stats */}
      <DmsStatsCards stats={stats} isLoading={statsLoading} />

      {/* Tabs */}
      <div className="flex gap-2">
        {([
          { key: 'upcoming' as const, label: `Upcoming (${upcoming.length})` },
          { key: 'past' as const, label: `Past (${past.length})` },
          { key: 'followups' as const, label: `Follow-ups (${allFollowups.length})` },
        ]).map((t) => (
          <button
            key={t.key}
            onClick={() => handleTabChange(t.key)}
            className={cn(
              'rounded-lg px-4 py-2 text-sm font-medium transition-colors',
              tab === t.key
                ? 'bg-indigo-600 text-white dark:bg-indigo-500'
                : 'bg-gray-200 text-gray-700 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Search (schedules tabs only) */}
      {tab !== 'followups' && (
        <div className="relative max-w-md">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => handleSearchChange(e.target.value)}
            placeholder="Search universitas..."
            className="w-full rounded-lg border border-gray-300 bg-white py-2 pl-10 pr-4 text-sm text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
          />
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <div className="flex justify-center py-12">
          <Spinner size="lg" />
        </div>
      ) : tab === 'followups' ? (
        <Card>
          <DmsFollowupTimeline followups={allFollowups} />
        </Card>
      ) : (
        <>
          <Card padding={false}>
            <DmsScheduleTable schedules={paged} researchedIds={researchedIds} sortKey={sortKey} sortDir={sortDir} onSort={handleSort} />
          </Card>

          {totalPages > 1 && (
            <Pagination
              currentPage={page}
              totalPages={totalPages}
              onPageChange={setPage}
            />
          )}

          <p className="text-center text-xs text-gray-400 dark:text-gray-500">
            Showing {paged.length} of {filtered.length} schedules
          </p>
        </>
      )}
    </div>
  )
}
