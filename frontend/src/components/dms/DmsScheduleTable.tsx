import { useNavigate } from 'react-router-dom'
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../ui/Table'
import { Badge } from '../ui/Badge'
import { EmptyState } from '../ui/EmptyState'
import { CalendarDays, Video, MapPin, ExternalLink, Building2, GraduationCap, ArrowUp, ArrowDown, ChevronsUpDown } from 'lucide-react'
import type { DmsSchedule } from '../../api/dms'

export type ScheduleSortKey = 'nama_universitas' | 'jadwal_audiensi' | 'type_meeting' | 'status_approval'
export type SortDir = 'asc' | 'desc'

interface Props {
  schedules: DmsSchedule[]
  isLoading?: boolean
  researchedIds?: Set<number>
  sortKey?: ScheduleSortKey | null
  sortDir?: SortDir
  onSort?: (key: ScheduleSortKey) => void
}

const APPROVAL_COLORS: Record<string, { bg: string; text: string }> = {
  Approved: {
    bg: 'bg-green-100 dark:bg-green-900/50',
    text: 'text-green-700 dark:text-green-300',
  },
  'Waiting for Approval': {
    bg: 'bg-yellow-100 dark:bg-yellow-900/50',
    text: 'text-yellow-700 dark:text-yellow-300',
  },
  Rejected: {
    bg: 'bg-red-100 dark:bg-red-900/50',
    text: 'text-red-700 dark:text-red-300',
  },
  diterima: {
    bg: 'bg-green-100 dark:bg-green-900/50',
    text: 'text-green-700 dark:text-green-300',
  },
  request: {
    bg: 'bg-blue-100 dark:bg-blue-900/50',
    text: 'text-blue-700 dark:text-blue-300',
  },
  pembuatan: {
    bg: 'bg-yellow-100 dark:bg-yellow-900/50',
    text: 'text-yellow-700 dark:text-yellow-300',
  },
  pengiriman: {
    bg: 'bg-purple-100 dark:bg-purple-900/50',
    text: 'text-purple-700 dark:text-purple-300',
  },
  akan_datang: {
    bg: 'bg-blue-100 dark:bg-blue-900/50',
    text: 'text-blue-700 dark:text-blue-300',
  },
  sedang_berjalan: {
    bg: 'bg-amber-100 dark:bg-amber-900/50',
    text: 'text-amber-700 dark:text-amber-300',
  },
  selesai: {
    bg: 'bg-green-100 dark:bg-green-900/50',
    text: 'text-green-700 dark:text-green-300',
  },
  terlambat: {
    bg: 'bg-red-100 dark:bg-red-900/50',
    text: 'text-red-700 dark:text-red-300',
  },
}

function meetingTypeLabel(type: string | null): string {
  if (!type) return '-'
  const lower = type.toLowerCase()
  if (lower.includes('zoom') || lower.includes('online')) return 'Zoom'
  if (lower.includes('offline') || lower.includes('luring')) return 'Offline'
  return type
}

function formatDateShort(dateStr: string | null): string {
  if (!dateStr) return '-'
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' })
  } catch {
    return dateStr
  }
}

function isPast(dateStr: string | null): boolean {
  if (!dateStr) return false
  const d = new Date(dateStr)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return d < today
}

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <ChevronsUpDown className="ml-1 inline h-3 w-3 text-gray-400" />
  return dir === 'asc'
    ? <ArrowUp className="ml-1 inline h-3 w-3 text-indigo-500" />
    : <ArrowDown className="ml-1 inline h-3 w-3 text-indigo-500" />
}

function SortableHead({
  label,
  sortKey: colKey,
  currentKey,
  currentDir,
  onSort,
  className,
}: {
  label: string
  sortKey: ScheduleSortKey
  currentKey?: ScheduleSortKey | null
  currentDir: SortDir
  onSort?: (key: ScheduleSortKey) => void
  className?: string
}) {
  return (
    <TableHead className={className}>
      <button
        type="button"
        className="inline-flex items-center gap-0.5 text-left font-medium hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
        onClick={() => onSort?.(colKey)}
      >
        {label}
        <SortIcon active={currentKey === colKey} dir={currentDir} />
      </button>
    </TableHead>
  )
}

export function DmsScheduleTable({ schedules, isLoading, researchedIds, sortKey, sortDir = 'asc', onSort }: Props) {
  const navigate = useNavigate()

  if (!isLoading && schedules.length === 0) {
    return (
      <EmptyState
        icon={CalendarDays}
        title="No schedules found"
        description="No audiensi schedules match the current filter."
      />
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-12">#</TableHead>
          <SortableHead label="Universitas" sortKey="nama_universitas" currentKey={sortKey} currentDir={sortDir} onSort={onSort} />
          <SortableHead label="Tanggal" sortKey="jadwal_audiensi" currentKey={sortKey} currentDir={sortDir} onSort={onSort} className="w-32" />
          <TableHead className="w-24">Jam</TableHead>
          <SortableHead label="Type" sortKey="type_meeting" currentKey={sortKey} currentDir={sortDir} onSort={onSort} className="w-24" />
          <SortableHead label="Status" sortKey="status_approval" currentKey={sortKey} currentDir={sortDir} onSort={onSort} className="w-32" />
          <TableHead className="w-24">Info</TableHead>
          <TableHead className="w-16 text-center">Rektor</TableHead>
          <TableHead className="w-16" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {schedules.map((s, idx) => {
          const past = isPast(s.jadwal_audiensi)
          const isLsp = s.source === 'schedule_follow_up_lsp'
          const approvalStyle = APPROVAL_COLORS[s.status_approval ?? ''] ?? {
            bg: 'bg-gray-100 dark:bg-gray-700',
            text: 'text-gray-600 dark:text-gray-400',
          }
          const mType = isLsp ? 'LSP' : meetingTypeLabel(s.type_meeting)

          return (
            <TableRow
              key={`${s.source}-${s.id}`}
              className={`cursor-pointer transition-colors hover:bg-gray-50 dark:hover:bg-gray-700/50 ${past ? 'opacity-60' : ''}`}
              onClick={() =>
                navigate(`/dms-schedules/${s.id}?source=${s.source}`)
              }
            >
              <TableCell className="font-mono text-xs text-gray-400">
                {idx + 1}
              </TableCell>
              <TableCell>
                <div className="flex flex-col">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-gray-900 dark:text-gray-100">
                      {s.nama_universitas ?? `Univ #${s.id_univ}`}
                    </span>
                    {isLsp && (
                      <Badge className="bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300 text-[10px] px-1.5 py-0">
                        LSP
                      </Badge>
                    )}
                  </div>
                  {s.alamat && (
                    <span className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
                      <MapPin className="h-3 w-3" />
                      {s.alamat.length > 50 ? s.alamat.slice(0, 50) + '...' : s.alamat}
                    </span>
                  )}
                </div>
              </TableCell>
              <TableCell className="whitespace-nowrap font-mono text-sm">
                {formatDateShort(s.jadwal_audiensi)}
              </TableCell>
              <TableCell className="whitespace-nowrap font-mono text-sm">
                {s.jam_audensi ?? '-'}
              </TableCell>
              <TableCell>
                <span className="inline-flex items-center gap-1 text-sm">
                  {mType === 'Zoom' ? (
                    <Video className="h-3.5 w-3.5 text-blue-500" />
                  ) : mType === 'LSP' ? (
                    <Building2 className="h-3.5 w-3.5 text-emerald-500" />
                  ) : (
                    <MapPin className="h-3.5 w-3.5 text-orange-500" />
                  )}
                  {mType}
                </span>
              </TableCell>
              <TableCell>
                {s.status_approval ? (
                  <Badge className={`${approvalStyle.bg} ${approvalStyle.text}`}>
                    {s.status_approval}
                  </Badge>
                ) : (
                  <span className="text-xs text-gray-400">-</span>
                )}
              </TableCell>
              <TableCell className="text-center text-sm">
                {isLsp
                  ? s.status_approval ?? '-'
                  : s.est_audiens != null
                    ? `${s.est_audiens} org`
                    : '-'}
              </TableCell>
              <TableCell className="text-center">
                {researchedIds?.has(s.id) ? (
                  <span title="Sudah diteliti">
                    <GraduationCap className="mx-auto h-4 w-4 text-green-500" />
                  </span>
                ) : (
                  <span className="text-xs text-gray-300 dark:text-gray-600">–</span>
                )}
              </TableCell>
              <TableCell>
                {s.link_zoom && (
                  <a
                    href={s.link_zoom}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="text-blue-600 hover:text-blue-800 dark:text-blue-400"
                  >
                    <ExternalLink className="h-4 w-4" />
                  </a>
                )}
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
