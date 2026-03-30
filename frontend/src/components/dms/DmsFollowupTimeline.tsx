import { Phone, Mail, MessageSquare, Globe, Users, Video } from 'lucide-react'
import { Badge } from '../ui/Badge'
import type { DmsFollowup } from '../../api/dms'

interface Props {
  followups: DmsFollowup[]
}

const METODE_MAP: Record<number, { label: string; icon: typeof Phone; color: string }> = {
  1: { label: 'Telepon', icon: Phone, color: 'text-blue-500' },
  2: { label: 'Email', icon: Mail, color: 'text-amber-500' },
  3: { label: 'WA Chat', icon: MessageSquare, color: 'text-green-500' },
  4: { label: 'Visit', icon: Users, color: 'text-purple-500' },
  5: { label: 'Website', icon: Globe, color: 'text-cyan-500' },
  6: { label: 'WhatsApp', icon: MessageSquare, color: 'text-green-600' },
  7: { label: 'Zoom', icon: Video, color: 'text-indigo-500' },
}

const HASIL_COLORS: Record<number, { bg: string; text: string; label: string }> = {
  1: {
    bg: 'bg-green-100 dark:bg-green-900/50',
    text: 'text-green-700 dark:text-green-300',
    label: 'Berhasil',
  },
  2: {
    bg: 'bg-yellow-100 dark:bg-yellow-900/50',
    text: 'text-yellow-700 dark:text-yellow-300',
    label: 'Terjadwal',
  },
  3: {
    bg: 'bg-red-100 dark:bg-red-900/50',
    text: 'text-red-700 dark:text-red-300',
    label: 'Gagal',
  },
  4: {
    bg: 'bg-gray-100 dark:bg-gray-700',
    text: 'text-gray-600 dark:text-gray-400',
    label: 'Tidak Dijawab',
  },
}

function formatTanggal(s: string | null): string {
  if (!s) return '-'
  try {
    const d = new Date(s)
    return d.toLocaleDateString('id-ID', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    })
  } catch {
    return s
  }
}

export function DmsFollowupTimeline({ followups }: Props) {
  if (followups.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-gray-500 dark:text-gray-400">
        No follow-up history yet.
      </p>
    )
  }

  return (
    <div className="relative space-y-0">
      {/* Vertical line */}
      <div className="absolute left-4 top-2 bottom-2 w-px bg-gray-200 dark:bg-gray-700" />

      {followups.map((f, idx) => {
        const metode = METODE_MAP[f.metode_followup ?? 0]
        const hasil = HASIL_COLORS[f.hasil_followup ?? 0]
        const Icon = metode?.icon ?? MessageSquare

        return (
          <div key={f.id ?? idx} className="relative flex gap-4 py-3 pl-0">
            {/* Dot */}
            <div className="relative z-10 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full border-2 border-gray-200 bg-white dark:border-gray-600 dark:bg-gray-800">
              <Icon className={`h-4 w-4 ${metode?.color ?? 'text-gray-400'}`} />
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {formatTanggal(f.tanggal_follow_up)}
                </span>
                {metode && (
                  <Badge className="bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300">
                    {metode.label}
                  </Badge>
                )}
                {hasil && (
                  <Badge className={`${hasil.bg} ${hasil.text}`}>{hasil.label}</Badge>
                )}
              </div>

              {f.nama_universitas && (
                <p className="mt-0.5 text-xs font-medium text-indigo-600 dark:text-indigo-400">
                  {f.nama_universitas}
                </p>
              )}

              {f.catatan && (
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-300 leading-relaxed">
                  {f.catatan}
                </p>
              )}

              {f.user_name && (
                <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                  by {f.user_name}
                </p>
              )}

              {f.next_follow_up_date && (
                <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                  Next follow-up: {formatTanggal(f.next_follow_up_date)}
                </p>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
