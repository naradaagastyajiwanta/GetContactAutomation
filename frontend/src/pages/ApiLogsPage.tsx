import { useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { ScrollText, ChevronDown, ChevronRight, Tag, BookOpen, Wrench, MessageSquare, Cpu } from 'lucide-react'
import { useApiLogs, useApiLog } from '../hooks/useApiLogs'
import { Card } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Spinner } from '../components/ui/Spinner'
import { EmptyState } from '../components/ui/EmptyState'
import { Pagination } from '../components/ui/Pagination'
import { Select } from '../components/ui/Select'
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../components/ui/Table'
import { formatDate } from '../lib/utils'

const PAGE_SIZE = 25

const CHATBOT_TYPE_OPTIONS = [
  { value: '', label: 'All Types' },
  { value: 'agent', label: 'Agent' },
  { value: 'audiensi', label: 'Audiensi' },
]

const CALL_TYPE_OPTIONS = [
  { value: '', label: 'All Calls' },
  { value: 'reply', label: 'Reply' },
  { value: 'initial', label: 'Initial' },
  { value: 'followup', label: 'Followup' },
]

const CHATBOT_BADGE: Record<string, string> = {
  agent: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  audiensi: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
}

const CALL_TYPE_BADGE: Record<string, string> = {
  reply: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  initial: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  followup: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
}

function LogDetailPanel({ logId }: { logId: number }) {
  const { data: log, isLoading } = useApiLog(logId)

  if (isLoading) {
    return (
      <div className="flex justify-center py-6">
        <Spinner />
      </div>
    )
  }

  if (!log) return null

  const situationTags: string[] = log.situation_tags ?? []
  const knowledgeItems = log.knowledge_items_injected ?? []
  const toolCalls: string[] = log.tool_calls_made ?? []
  const messagesSent = log.messages_sent ?? []

  return (
    <div className="space-y-4 border-t border-gray-200 bg-gray-50 px-4 py-4 dark:border-gray-700 dark:bg-gray-800/50">
      {/* Token Usage */}
      <div className="flex items-center gap-4">
        <Cpu className="h-4 w-4 text-gray-400" />
        <span className="text-xs text-gray-500 dark:text-gray-400">
          Prompt: <strong>{log.prompt_tokens}</strong>
          {log.cached_tokens > 0 && (
            <span className="text-green-600 dark:text-green-400"> ({log.cached_tokens} cached, 50% off)</span>
          )}
          {' | '}Completion: <strong>{log.completion_tokens}</strong> | Total: <strong>{log.total_tokens}</strong>
        </span>
      </div>

      {/* Situation Tags */}
      {situationTags.length > 0 && (
        <div>
          <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-gray-500 dark:text-gray-400">
            <Tag className="h-3.5 w-3.5" />
            Situation Tags
          </div>
          <div className="flex flex-wrap gap-1">
            {situationTags.map((tag) => (
              <Badge key={tag} className="bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300">
                {tag}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* Knowledge Items */}
      {knowledgeItems.length > 0 && (
        <div>
          <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-gray-500 dark:text-gray-400">
            <BookOpen className="h-3.5 w-3.5" />
            Knowledge Items Injected ({knowledgeItems.length})
          </div>
          <ul className="space-y-1">
            {knowledgeItems.map((ki) => (
              <li key={ki.id} className="text-xs text-gray-600 dark:text-gray-400">
                <span className="font-medium">{ki.title}</span>
                {ki.tags && (
                  <span className="ml-1 text-gray-400 dark:text-gray-500">({ki.tags})</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Tool Calls */}
      {toolCalls.length > 0 && (
        <div>
          <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-gray-500 dark:text-gray-400">
            <Wrench className="h-3.5 w-3.5" />
            Tool Calls
          </div>
          <div className="flex flex-wrap gap-1">
            {toolCalls.map((tc, i) => (
              <Badge key={`${tc}-${i}`} className="bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300">
                {tc}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* Response Text */}
      {log.response_text && (
        <div>
          <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-gray-500 dark:text-gray-400">
            <MessageSquare className="h-3.5 w-3.5" />
            Response Text
          </div>
          <div className="rounded-md border border-gray-200 bg-white p-3 text-sm text-gray-700 whitespace-pre-wrap dark:border-gray-600 dark:bg-gray-900 dark:text-gray-300">
            {log.response_text}
          </div>
        </div>
      )}

      {/* System Prompt */}
      {log.system_prompt && (
        <details className="group">
          <summary className="cursor-pointer text-xs font-medium text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200">
            System Prompt (click to expand)
          </summary>
          <pre className="mt-2 max-h-64 overflow-auto rounded-md border border-gray-200 bg-white p-3 text-xs text-gray-600 whitespace-pre-wrap dark:border-gray-600 dark:bg-gray-900 dark:text-gray-400">
            {log.system_prompt}
          </pre>
        </details>
      )}

      {/* Messages Sent */}
      {messagesSent.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-xs font-medium text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200">
            Messages Sent ({messagesSent.length} messages, click to expand)
          </summary>
          <div className="mt-2 max-h-64 space-y-2 overflow-auto">
            {messagesSent.map((msg, i) => (
              <div key={i} className="rounded-md border border-gray-200 bg-white p-2 dark:border-gray-600 dark:bg-gray-900">
                <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                  {msg.role}
                </span>
                <p className="mt-0.5 text-xs text-gray-600 whitespace-pre-wrap dark:text-gray-400">
                  {typeof msg.content === 'string' ? msg.content.slice(0, 500) : JSON.stringify(msg.content).slice(0, 500)}
                  {typeof msg.content === 'string' && msg.content.length > 500 ? '...' : ''}
                </p>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}

export default function ApiLogsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [page, setPage] = useState(1)

  const chatbotType = searchParams.get('chatbot_type') || ''
  const callType = searchParams.get('call_type') || ''
  const conversationId = searchParams.get('conversation_id')

  const params = {
    ...(chatbotType && { chatbot_type: chatbotType }),
    ...(callType && { call_type: callType }),
    ...(conversationId && { conversation_id: Number(conversationId) }),
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  }

  const { data, isLoading } = useApiLogs(params)
  const logs = data?.logs ?? []

  const updateFilter = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams)
    if (value) {
      next.set(key, value)
    } else {
      next.delete(key)
    }
    setSearchParams(next)
    setPage(1)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <ScrollText className="h-6 w-6 text-indigo-600 dark:text-indigo-400" />
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">API Logs</h1>
      </div>

      {/* Filters */}
      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <Select
            value={chatbotType}
            onChange={(v) => updateFilter('chatbot_type', v)}
            options={CHATBOT_TYPE_OPTIONS}
          />
          <Select
            value={callType}
            onChange={(v) => updateFilter('call_type', v)}
            options={CALL_TYPE_OPTIONS}
          />
          {conversationId && (
            <div className="flex items-center gap-1">
              <Badge className="bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300">
                Conv #{conversationId}
              </Badge>
              <button
                className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                onClick={() => updateFilter('conversation_id', '')}
              >
                clear
              </button>
            </div>
          )}
        </div>
      </Card>

      {/* Table */}
      {isLoading ? (
        <div className="flex justify-center py-12">
          <Spinner size="lg" />
        </div>
      ) : logs.length === 0 ? (
        <EmptyState
          icon={ScrollText}
          title="No API logs found"
          description="API call logs will appear here once the chatbot processes messages."
        />
      ) : (
        <Card padding={false}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Time</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Call</TableHead>
                <TableHead>Conv</TableHead>
                <TableHead>Model</TableHead>
                <TableHead>Tokens</TableHead>
                <TableHead>Tags</TableHead>
                <TableHead>KB</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {logs.map((logEntry) => {
                const isExpanded = expandedId === logEntry.id
                const situationTags: string[] = logEntry.situation_tags ?? []
                const kbItems = logEntry.knowledge_items_injected ?? []

                return (
                  <tr key={logEntry.id} className="group">
                    <td colSpan={9} className="p-0">
                      <div
                        className="flex cursor-pointer items-center hover:bg-gray-50 dark:hover:bg-gray-800/50"
                        onClick={() => setExpandedId(isExpanded ? null : logEntry.id)}
                      >
                        <TableCell className="w-8 pr-0">
                          {isExpanded ? (
                            <ChevronDown className="h-4 w-4 text-gray-400" />
                          ) : (
                            <ChevronRight className="h-4 w-4 text-gray-400" />
                          )}
                        </TableCell>
                        <TableCell className="whitespace-nowrap">
                          {formatDate(logEntry.created_at)}
                        </TableCell>
                        <TableCell>
                          <Badge className={CHATBOT_BADGE[logEntry.chatbot_type] || ''}>
                            {logEntry.chatbot_type}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Badge className={CALL_TYPE_BADGE[logEntry.call_type] || ''}>
                            {logEntry.call_type}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {logEntry.conversation_id ? (
                            <Link
                              to={`/conversations/${logEntry.conversation_id}`}
                              className="text-indigo-600 hover:underline dark:text-indigo-400"
                              onClick={(e) => e.stopPropagation()}
                            >
                              #{logEntry.conversation_id}
                            </Link>
                          ) : (
                            <span className="text-gray-400">-</span>
                          )}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {logEntry.model_used || '-'}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {logEntry.total_tokens}
                        </TableCell>
                        <TableCell className="text-xs">
                          {situationTags.length || '-'}
                        </TableCell>
                        <TableCell className="text-xs">
                          {kbItems.length || '-'}
                        </TableCell>
                      </div>
                      {isExpanded && <LogDetailPanel logId={logEntry.id} />}
                    </td>
                  </tr>
                )
              })}
            </TableBody>
          </Table>

          {/* Pagination */}
          {logs.length >= PAGE_SIZE && (
            <div className="flex justify-center border-t border-gray-200 py-3 dark:border-gray-700">
              <Pagination
                currentPage={page}
                totalPages={page + 1}
                onPageChange={setPage}
              />
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
