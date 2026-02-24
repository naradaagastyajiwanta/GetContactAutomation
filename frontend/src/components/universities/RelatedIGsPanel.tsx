import { ExternalLink, Users, CheckCircle, Clock } from 'lucide-react'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../ui/Table'
import { EmptyState } from '../ui/EmptyState'
import { Badge } from '../ui/Badge'
import { formatDate } from '../../lib/utils'
import type { RelatedIg } from '../../lib/types'

interface RelatedIGsPanelProps {
  relatedIgs: RelatedIg[]
}

const RELATION_COLORS: Record<string, { bg: string; text: string }> = {
  bem: { bg: 'bg-purple-100 dark:bg-purple-900/30', text: 'text-purple-700 dark:text-purple-300' },
  humas: { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-700 dark:text-blue-300' },
  pmb: { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-700 dark:text-green-300' },
  kemahasiswaan: { bg: 'bg-amber-100 dark:bg-amber-900/30', text: 'text-amber-700 dark:text-amber-300' },
  alumni: { bg: 'bg-gray-100 dark:bg-gray-800', text: 'text-gray-700 dark:text-gray-300' },
  lppm: { bg: 'bg-teal-100 dark:bg-teal-900/30', text: 'text-teal-700 dark:text-teal-300' },
}

export function RelatedIGsPanel({ relatedIgs }: RelatedIGsPanelProps) {
  if (relatedIgs.length === 0) {
    return (
      <EmptyState
        icon={Users}
        title="No related IG accounts"
        description="No BEM or related Instagram accounts have been discovered yet. Run the BEM discovery agent to find them."
      />
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Handle</TableHead>
          <TableHead>Type</TableHead>
          <TableHead>Source</TableHead>
          <TableHead>Confidence</TableHead>
          <TableHead>Posts Scraped</TableHead>
          <TableHead>Discovered</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {relatedIgs.map((ig) => {
          const colors = RELATION_COLORS[ig.relation_type] || RELATION_COLORS.bem
          return (
            <TableRow key={ig.id}>
              <TableCell>
                <a
                  href={`https://instagram.com/${ig.ig_handle}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
                >
                  @{ig.ig_handle}
                  <ExternalLink className="h-3 w-3" />
                </a>
              </TableCell>
              <TableCell>
                <Badge className={`${colors.bg} ${colors.text}`}>
                  {ig.relation_type}
                </Badge>
              </TableCell>
              <TableCell className="text-sm text-gray-500 dark:text-gray-400">
                {ig.source}
              </TableCell>
              <TableCell>
                <span className="text-sm font-medium">
                  {(ig.confidence * 100).toFixed(0)}%
                </span>
              </TableCell>
              <TableCell>
                {ig.posts_scraped ? (
                  <CheckCircle className="h-4 w-4 text-green-500" />
                ) : (
                  <Clock className="h-4 w-4 text-gray-400" />
                )}
              </TableCell>
              <TableCell className="text-sm text-gray-500 dark:text-gray-400">
                {formatDate(ig.discovered_at)}
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
