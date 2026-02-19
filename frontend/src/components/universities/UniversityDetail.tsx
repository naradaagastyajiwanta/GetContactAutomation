import { ExternalLink } from 'lucide-react'
import { Card, CardContent } from '../ui/Card'
import { Badge } from '../ui/Badge'
import { STATUS_COLORS } from '../../lib/constants'
import { formatDate } from '../../lib/utils'
import type { University } from '../../lib/types'

interface UniversityDetailProps {
  university: University
}

export function UniversityDetail({ university }: UniversityDetailProps) {
  const colors = STATUS_COLORS[university.status] || STATUS_COLORS.pending

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
              <a
                href={`https://instagram.com/${university.ig_handle}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
              >
                @{university.ig_handle}
                <ExternalLink className="h-3 w-3" />
              </a>
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

          <InfoRow label="IG Verified">
            {university.ig_verified ? 'Yes' : 'No'}
          </InfoRow>

          <InfoRow label="PDDIKTI ID">
            {university.pddikti_id || '-'}
          </InfoRow>

          <InfoRow label="Created">
            {formatDate(university.created_at)}
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
