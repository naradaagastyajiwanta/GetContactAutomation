/**
 * EmailLetterHistory — shows all sent letter numbers with duplicate detection.
 */

import { useState, useMemo } from 'react'
import {
  FileText,
  RefreshCw,
  Search,
  AlertTriangle,
  Copy,
  Check,
  ChevronUp,
  ChevronDown,
  Mail,
} from 'lucide-react'
import { cn, formatRelative } from '../../lib/utils'
import { useLetterHistory } from '../../hooks/useEmailBlast'
import { Spinner } from '../ui/Spinner'
import { EmptyState } from '../ui/EmptyState'
import type { LetterHistoryItem } from '../../api/emailBlast'

type SortField = 'letter_number' | 'university_name' | 'campaign_name' | 'email' | 'sent_at' | 'is_duplicate'
type SortDir = 'asc' | 'desc'

const PAGE_SIZE = 50

function DuplicateBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
      <AlertTriangle className="h-3 w-3" />
      Duplicate
    </span>
  )
}

function SortHeader({
  label,
  field,
  current,
  dir,
  onSort,
}: {
  label: string
  field: SortField
  current: SortField
  dir: SortDir
  onSort: (f: SortField, d: SortDir) => void
}) {
  const active = current === field
  return (
    <button
      onClick={() => onSort(field, active && dir === 'asc' ? 'desc' : 'asc')}
      className={cn(
        'flex items-center gap-1 text-left text-[11px] font-semibold uppercase tracking-wider transition-colors',
        active ? 'text-indigo-600 dark:text-indigo-400' : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300',
      )}
    >
      {label}
      {active && dir === 'asc' && <ChevronUp className="h-3 w-3" />}
      {active && dir === 'desc' && <ChevronDown className="h-3 w-3" />}
    </button>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation()
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }
  return (
    <button
      onClick={handleCopy}
      className="rounded p-0.5 text-gray-400 transition-colors hover:text-indigo-600"
      title="Copy"
    >
      {copied ? <Check className="h-3 w-3 text-green-500" /> : <Copy className="h-3 w-3" />}
    </button>
  )
}

export function EmailLetterHistory() {
  const [campaignFilter, setCampaignFilter] = useState<number | undefined>(undefined)
  const [duplicateOnly, setDuplicateOnly] = useState(false)
  const [search, setSearch] = useState('')
  const [sortField, setSortField] = useState<SortField>('sent_at')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const { data, isLoading, isFetching, refetch } = useLetterHistory({
    campaign_id: campaignFilter,
    duplicate_only: duplicateOnly,
    search: search || undefined,
    limit: PAGE_SIZE,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const duplicateCount = data?.duplicate_count ?? 0

  // Build campaign filter list
  const campaigns = useMemo(() => {
    const map = new Map<number, string>()
    items.forEach((i: LetterHistoryItem) => map.set(i.campaign_id, i.campaign_name))
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }))
  }, [items])

  // Sort items
  const sorted = useMemo(() => {
    return [...items].sort((a, b) => {
      let av: string | boolean = ''
      let bv: string | boolean = ''
      switch (sortField) {
        case 'letter_number': av = a.letter_number; bv = b.letter_number; break
        case 'university_name': av = a.university_name ?? ''; bv = b.university_name ?? ''; break
        case 'campaign_name': av = a.campaign_name; bv = b.campaign_name; break
        case 'email': av = a.email; bv = b.email; break
        case 'sent_at': av = a.sent_at ?? ''; bv = b.sent_at ?? ''; break
        case 'is_duplicate': av = a.is_duplicate; bv = b.is_duplicate; break
      }
      if (typeof av === 'boolean') {
        return sortDir === 'asc'
          ? (av === bv ? 0 : av ? 1 : -1)
          : (av === bv ? 0 : av ? -1 : 1)
      }
      const cmp = String(av).localeCompare(String(bv))
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [items, sortField, sortDir])

  function handleSort(field: SortField, dir: SortDir) {
    setSortField(field)
    setSortDir(dir)
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-gray-100 bg-white px-6 py-4 dark:border-gray-800 dark:bg-[#111827]">
        <div className="flex items-center gap-3">
          <FileText className="h-5 w-5 text-indigo-600" />
          <h1 className="text-base font-semibold text-gray-900 dark:text-white">Riwayat Surat</h1>
          <div className="flex items-center gap-2">
            {duplicateCount > 0 && (
              <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-[11px] font-semibold text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                {duplicateCount} duplikat
              </span>
            )}
            <span className="text-[12px] text-gray-400 dark:text-gray-500">
              {total.toLocaleString('id-ID')} surat
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-[12px] font-medium text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800"
          >
            <RefreshCw className={cn('h-3.5 w-3.5', isFetching && 'animate-spin')} />
            Refresh
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-gray-100 bg-white px-6 py-3 dark:border-gray-800 dark:bg-[#0f172a]">
        {/* Search */}
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Cari nomor surat, universitas, campaign, pengirim..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 w-64 rounded-lg border border-gray-200 bg-white pl-8 pr-3 text-[12px] text-gray-900 placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-white dark:placeholder:text-gray-500"
          />
        </div>

        {/* Campaign filter */}
        <select
          value={campaignFilter ?? ''}
          onChange={(e) => setCampaignFilter(e.target.value ? Number(e.target.value) : undefined)}
          className="h-8 rounded-lg border border-gray-200 bg-white px-2 text-[12px] text-gray-700 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300"
        >
          <option value="">Semua Campaign</option>
          {campaigns.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>

        {/* Duplicate only toggle */}
        <button
          onClick={() => setDuplicateOnly((v) => !v)}
          className={cn(
            'flex h-8 items-center gap-1.5 rounded-lg border px-3 text-[12px] font-medium transition-colors',
            duplicateOnly
              ? 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-400'
              : 'border-gray-200 text-gray-500 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800',
          )}
        >
          <AlertTriangle className="h-3.5 w-3.5" />
          Duplikat saja
        </button>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex flex-1 items-center justify-center">
          <Spinner />
        </div>
      ) : sorted.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="Belum ada riwayat surat"
          description="Surat akan muncul di sini setelah campaign dimulai dan email berhasil dikirim."
        />
      ) : (
        <div className="flex-1 overflow-auto">
          <table className="w-full border-collapse text-[12px]">
            <thead className="sticky top-0 z-10 bg-gray-50 dark:bg-[#0f172a]">
              <tr className="border-b border-gray-100 dark:border-gray-800">
                <th className="px-4 py-2.5 text-left">
                  <SortHeader label="No. Surat" field="letter_number" current={sortField} dir={sortDir} onSort={handleSort} />
                </th>
                <th className="px-4 py-2.5 text-left">
                  <SortHeader label="Universitas" field="university_name" current={sortField} dir={sortDir} onSort={handleSort} />
                </th>
                <th className="px-4 py-2.5 text-left">
                  <SortHeader label="Campaign" field="campaign_name" current={sortField} dir={sortDir} onSort={handleSort} />
                </th>
                <th className="px-4 py-2.5 text-left">
                  <SortHeader label="Email" field="email" current={sortField} dir={sortDir} onSort={handleSort} />
                </th>
                <th className="px-4 py-2.5 text-left">
                  <SortHeader label="Status" field="is_duplicate" current={sortField} dir={sortDir} onSort={handleSort} />
                </th>
                <th className="px-4 py-2.5 text-left">
                  <SortHeader label="Terkirim" field="sent_at" current={sortField} dir={sortDir} onSort={handleSort} />
                </th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((item) => (
                <tr
                  key={item.id}
                  className="border-b border-gray-50 transition-colors hover:bg-gray-50/70 dark:border-gray-800/60 dark:hover:bg-gray-800/30"
                >
                  {/* Letter number */}
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono text-[11px] font-semibold text-gray-800 dark:text-gray-200">
                        {item.letter_number || '—'}
                      </span>
                      {item.letter_number && <CopyButton text={item.letter_number} />}
                    </div>
                  </td>

                  {/* University */}
                  <td className="px-4 py-2.5">
                    <span className="text-gray-700 dark:text-gray-300">{item.university_name ?? '—'}</span>
                  </td>

                  {/* Campaign */}
                  <td className="px-4 py-2.5">
                    <div>
                      <span className="text-gray-500 dark:text-gray-400">{item.campaign_name}</span>
                      {(item.started_by_name || item.started_by_email) && (
                        <p className="mt-0.5 text-[11px] text-gray-400 dark:text-gray-500">
                          Dijalankan oleh {item.started_by_name || item.started_by_email}
                        </p>
                      )}
                    </div>
                  </td>

                  {/* Email */}
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-1">
                      <Mail className="h-3 w-3 shrink-0 text-gray-400" />
                      <span className="truncate text-gray-500 dark:text-gray-400">{item.email}</span>
                    </div>
                  </td>

                  {/* Status */}
                  <td className="px-4 py-2.5">
                    {item.is_duplicate ? <DuplicateBadge /> : (
                      <span className="text-[11px] text-gray-400 dark:text-gray-500">Normal</span>
                    )}
                  </td>

                  {/* Sent at */}
                  <td className="px-4 py-2.5">
                    <span className="text-gray-400 dark:text-gray-500">
                      {item.sent_at ? formatRelative(item.sent_at) : '—'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
