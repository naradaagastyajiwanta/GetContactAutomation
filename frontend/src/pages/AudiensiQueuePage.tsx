import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ClipboardList } from 'lucide-react'
import { useAudiensiQueue, useAudiensiConversations } from '../hooks/useAudiensi'
import { AudiensiApprovalCard } from '../components/audiensi/AudiensiApprovalCard'
import { AudiensiTemplateUpload } from '../components/audiensi/AudiensiTemplateUpload'
import { Badge } from '../components/ui/Badge'
import { Select } from '../components/ui/Select'
import { Spinner } from '../components/ui/Spinner'
import { EmptyState } from '../components/ui/EmptyState'
import { Pagination } from '../components/ui/Pagination'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../components/ui/Table'
import { AUDIENSI_STATES, AUDIENSI_STATE_COLORS, ITEMS_PER_PAGE } from '../lib/constants'
import { formatRelative } from '../lib/utils'
import { cn } from '../lib/utils'
import { useAuth } from '../context/AuthContext'

type Tab = 'pending' | 'all' | 'template'

const stateOptions = [
  { value: '', label: 'All States' },
  ...AUDIENSI_STATES.map((s) => ({ value: s, label: s.replace(/_/g, ' ') })),
]

export default function AudiensiQueuePage() {
  const { hasPermission } = useAuth()
  const [tab, setTab] = useState<Tab>('pending')
  const [state, setState] = useState('')
  const [page, setPage] = useState(1)
  const navigate = useNavigate()

  const offset = (page - 1) * ITEMS_PER_PAGE

  const { data: queue, isLoading: queueLoading } = useAudiensiQueue()
  const { data: conversations, isLoading: conversationsLoading } = useAudiensiConversations({
    state: state || undefined,
    limit: ITEMS_PER_PAGE,
    offset,
  })

  const handleStateChange = (newState: string) => {
    setState(newState)
    setPage(1)
  }

  const isLoading = tab === 'pending' ? queueLoading : tab === 'all' ? conversationsLoading : false
  const canManageAudiensi = hasPermission('audiensi.manage')

  const totalPages = conversations
    ? Math.max(1, Math.ceil(conversations.length / ITEMS_PER_PAGE) + (conversations.length === ITEMS_PER_PAGE ? 1 : 0))
    : 1

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Audiensi Queue</h1>
          {queue && queue.length > 0 && (
            <Badge className="bg-indigo-100 text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-300">
              {queue.length} pending
            </Badge>
          )}
        </div>

        {tab === 'all' && (
          <Select
            value={state}
            onChange={handleStateChange}
            options={stateOptions}
            className="w-48"
          />
        )}
      </div>

      {/* Tab buttons */}
      <div className="flex gap-2">
        <button
          onClick={() => setTab('pending')}
          className={cn(
            'rounded-lg px-4 py-2 text-sm font-medium transition-colors',
            tab === 'pending'
              ? 'bg-indigo-600 text-white dark:bg-indigo-500'
              : 'bg-gray-200 text-gray-700 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600',
          )}
        >
          Pending Approval
        </button>
        <button
          onClick={() => { setTab('all'); setPage(1) }}
          className={cn(
            'rounded-lg px-4 py-2 text-sm font-medium transition-colors',
            tab === 'all'
              ? 'bg-indigo-600 text-white dark:bg-indigo-500'
              : 'bg-gray-200 text-gray-700 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600',
          )}
        >
          All Conversations
        </button>
        {canManageAudiensi && (
          <button
            onClick={() => setTab('template')}
            className={cn(
              'rounded-lg px-4 py-2 text-sm font-medium transition-colors',
              tab === 'template'
                ? 'bg-indigo-600 text-white dark:bg-indigo-500'
                : 'bg-gray-200 text-gray-700 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600',
            )}
          >
            Template Surat
          </button>
        )}
      </div>

      {/* Content */}
      {tab === 'template' ? (
        <AudiensiTemplateUpload />
      ) : isLoading ? (
        <div className="flex justify-center py-12">
          <Spinner size="lg" />
        </div>
      ) : tab === 'pending' ? (
        /* Pending Approval Tab */
        !queue || queue.length === 0 ? (
          <EmptyState
            icon={ClipboardList}
            title="No pending approvals"
            description="There are no audiensi conversations waiting for approval."
          />
        ) : (
          <div className="space-y-4">
            {queue.map((conv) => (
              <AudiensiApprovalCard key={conv.id} conversation={conv} />
            ))}
          </div>
        )
      ) : (
        /* All Conversations Tab */
        !conversations || conversations.length === 0 ? (
          <EmptyState
            icon={ClipboardList}
            title="No audiensi conversations"
            description="No audiensi conversations match the current filter. Try changing the state filter."
          />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>University</TableHead>
                  <TableHead>Phone</TableHead>
                  <TableHead>State</TableHead>
                  <TableHead>Rector</TableHead>
                  <TableHead>Last Message</TableHead>
                  <TableHead>Attempts</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {conversations.map((conv) => {
                  const colors = AUDIENSI_STATE_COLORS[conv.state] ?? {
                    bg: 'bg-gray-100 dark:bg-gray-700',
                    text: 'text-gray-700 dark:text-gray-300',
                  }
                  return (
                    <TableRow
                      key={conv.id}
                      className="cursor-pointer"
                      onClick={() => navigate(`/audiensi/${conv.id}`)}
                    >
                      <TableCell className="font-medium">
                        {conv.university_name ?? `University #${conv.university_id}`}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {conv.contact_phone}
                      </TableCell>
                      <TableCell>
                        <Badge className={`${colors.bg} ${colors.text}`}>
                          {conv.state.replace(/_/g, ' ')}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {conv.rector_name || (
                          <span className="text-gray-400 dark:text-gray-500">-</span>
                        )}
                      </TableCell>
                      <TableCell>{formatRelative(conv.last_message_at)}</TableCell>
                      <TableCell>{conv.attempt_count}</TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
            <div className="flex justify-center">
              <Pagination
                currentPage={page}
                totalPages={totalPages}
                onPageChange={setPage}
              />
            </div>
          </>
        )
      )}
    </div>
  )
}
