import { useState } from 'react'
import { ExternalLink, Trash2 } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { Card, CardContent } from '../ui/Card'
import { Badge } from '../ui/Badge'
import { STATUS_COLORS } from '../../lib/constants'
import { formatDate } from '../../lib/utils'
import { resetUniversityIgHandle } from '../../api/universities'
import type { University } from '../../lib/types'

interface UniversityDetailProps {
  university: University
}

export function UniversityDetail({ university }: UniversityDetailProps) {
  const colors = STATUS_COLORS[university.status] || STATUS_COLORS.pending
  const queryClient = useQueryClient()
  const [resetting, setResetting] = useState(false)

  async function handleResetIgHandle() {
    if (!university.ig_handle) return
    const ok = window.confirm(
      `Hapus IG handle @${university.ig_handle}?\nStatus akan kembali ke "pending" dan akan dicari ulang oleh sistem.`
    )
    if (!ok) return
    setResetting(true)
    try {
      await resetUniversityIgHandle(university.id)
      queryClient.invalidateQueries({ queryKey: ['university', university.id] })
    } catch (e) {
      console.error('Reset IG handle failed:', e)
    } finally {
      setResetting(false)
    }
  }

  return (
    <Card>
      <CardContent>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
              {university.name}
            </h2>
            {university.province && (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {university.province}
              </p>
            )}
          </div>
          <Badge className={`${colors.bg} ${colors.text}`}>
            {university.status}
          </Badge>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <InfoRow label="IG Handle">
            {university.ig_handle ? (
              <span className="inline-flex items-center gap-2">
                <a
                  href={`https://instagram.com/${university.ig_handle}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
                >
                  @{university.ig_handle}
                  <ExternalLink className="h-3 w-3" />
                </a>
                <button
                  onClick={handleResetIgHandle}
                  disabled={resetting}
                  title="Hapus IG handle (reset ke pending)"
                  className="inline-flex items-center rounded p-0.5 text-red-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-50 dark:hover:bg-red-900/20 dark:hover:text-red-400"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </span>
            ) : (
              '-'
            )}
          </InfoRow>

          <InfoRow label="Website">
            {university.website ? (
              <a
                href={university.website}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
              >
                {university.website}
                <ExternalLink className="h-3 w-3" />
              </a>
            ) : (
              '-'
            )}
          </InfoRow>

          <InfoRow label="Phone">
            {university.secretariat_phone || '-'}
          </InfoRow>

          <InfoRow label="Email">
            {university.email_kampus ? (
              <span className="inline-flex items-center gap-2">
                <a
                  href={`mailto:${university.email_kampus}`}
                  className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
                >
                  {university.email_kampus}
                </a>
                {university.email_source && (
                  <span className="text-xs text-gray-400 dark:text-gray-500">
                    ({university.email_source})
                  </span>
                )}
              </span>
            ) : (
              '-'
            )}
          </InfoRow>

          <InfoRow label="IG Verified">
            {university.ig_verified ? 'Yes' : 'No'}
          </InfoRow>

          <InfoRow label="PDDIKTI ID">
            {university.pddikti_id || '-'}
          </InfoRow>

          <InfoRow label="Created">
            {formatDate(university.created_at)}
          </InfoRow>

          <InfoRow label="Rector">
            {university.rector_name || '-'}
          </InfoRow>

          <InfoRow label="Student Count">
            {university.student_count ? university.student_count.toLocaleString('id-ID') : '-'}
          </InfoRow>
        </div>
      </CardContent>
    </Card>
  )
}

function InfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <span className="text-xs font-medium uppercase text-gray-500 dark:text-gray-400">
        {label}
      </span>
      <div className="mt-0.5 text-sm text-gray-900 dark:text-gray-100">
        {children}
      </div>
    </div>
  )
}
