/**
 * EmailInboxView — Gmail-style inbox for inbound reply emails.
 */

import { useState, memo, useEffect, useRef } from 'react'
import {
  Inbox,
  RefreshCw,
  Search,
  Star,
  StarOff,
  Mail,
  ChevronRight,
} from 'lucide-react'
import { cn, formatRelative } from '../../lib/utils'
import { useAllInboxEmailsPaginated } from '../../hooks/useEmailBlast'
import type { InboundEmail } from '../../api/emailBlast'
import { Spinner } from '../ui/Spinner'
import { EmptyState } from '../ui/EmptyState'

interface Props {
  onViewChange?: (view: string, campaignId?: number) => void
  onEmailClick?: (email: unknown) => void
}

const EmailRow = memo(function EmailRow({
  email,
  isSelected,
  onSelect,
  onClick,
}: {
  email: InboundEmail
  isSelected: boolean
  onSelect: (id: number, checked: boolean) => void
  onClick: () => void
}) {
  const [starred, setStarred] = useState(false)
  const bodyPreview = email.body?.replace(/<[^>]+>/g, '').slice(0, 80) ?? ''

  return (
    <div
      onClick={onClick}
      className={cn(
        'group flex cursor-pointer items-center gap-3 border-b border-gray-50 px-4 py-3 transition-colors hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/50',
        isSelected && 'bg-indigo-50 dark:bg-indigo-950/30',
      )}
    >
      {/* Checkbox */}
      <input
        type="checkbox"
        checked={isSelected}
        onChange={(e) => {
          e.stopPropagation()
          onSelect(email.id, e.target.checked)
        }}
        onClick={(e) => e.stopPropagation()}
        className="h-4 w-4 shrink-0 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
      />

      {/* Star */}
      <button
        onClick={(e) => {
          e.stopPropagation()
          setStarred((s) => !s)
        }}
        className="shrink-0 text-gray-300 hover:text-yellow-500 transition-colors"
      >
        {starred ? <Star className="h-4 w-4 fill-yellow-400 text-yellow-400" /> : <StarOff className="h-4 w-4" />}
      </button>

      {/* Sender info */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              'truncate text-[13px] font-medium',
              isSelected ? 'text-indigo-700 dark:text-indigo-300' : 'text-gray-900 dark:text-gray-100',
            )}
          >
            {email.from_name || email.from_email}
          </span>
          {email.subject && (
            <span className="shrink-0 text-xs text-gray-400">— {email.subject.replace(/^Re:\s*/i, '')}</span>
          )}
        </div>
        <div className="truncate text-[12px] text-gray-500 dark:text-gray-400">
          {bodyPreview}
        </div>
      </div>

      {/* Time + arrow */}
      <div className="flex shrink-0 items-center gap-2">
        <span className="text-[11px] text-gray-400 dark:text-gray-500">
          {formatRelative(email.date)}
        </span>
        <ChevronRight className="h-4 w-4 text-gray-300 opacity-0 transition-opacity group-hover:opacity-100" />
      </div>
    </div>
  )
})

function EmailDetailPane({
  email,
  onClose,
}: {
  email: InboundEmail | null
  onClose: () => void
}) {
  if (!email) return null

  return (
    <div className="flex h-full w-[480px] shrink-0 flex-col border-l border-gray-200 bg-white dark:border-gray-700 dark:bg-[#111827]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3 dark:border-gray-800">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Email</h3>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
        >
          ✕
        </button>
      </div>

      {/* Meta */}
      <div className="border-b border-gray-100 px-5 py-4 dark:border-gray-800">
        <div className="mb-3 flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-indigo-600 dark:bg-indigo-900 dark:text-indigo-400">
            <Mail className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-gray-900 dark:text-white">
              {email.from_name || email.from_email}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              From: {email.from_email}
            </p>
          </div>
        </div>

        <div className="mb-1 text-sm text-gray-700 dark:text-gray-200">
          <span className="font-medium">Subject: </span>
          {email.subject || '(no subject)'}
        </div>
        <div className="text-xs text-gray-400 dark:text-gray-500">
          {new Date(email.date).toLocaleString('id-ID', {
            weekday: 'long',
            day: 'numeric',
            month: 'long',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          })}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        <div className="whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-200 leading-relaxed">
          {email.body}
        </div>
      </div>
    </div>
  )
}

export function EmailInboxView({ onViewChange }: Props) {
  const [search, setSearch] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [detailEmail, setDetailEmail] = useState<InboundEmail | null>(null)
  const loadMoreRef = useRef<HTMLDivElement>(null)

  const PAGE_SIZE = 50
  const {
    data,
    isLoading,
    refetch,
    isFetching,
    isError,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useAllInboxEmailsPaginated(PAGE_SIZE)

  // Flatten all pages into a single array
  const emails: InboundEmail[] = data?.pages.flatMap((page) => (page.emails as InboundEmail[]) ?? []) ?? []
  const total = data?.pages[0]?.total ?? 0

  const filtered = search.trim()
    ? emails.filter(
        (e) =>
          (e.from_name ?? '').toLowerCase().includes(search.toLowerCase()) ||
          (e.from_email ?? '').toLowerCase().includes(search.toLowerCase()) ||
          (e.subject ?? '').toLowerCase().includes(search.toLowerCase()) ||
          (e.body ?? '').toLowerCase().includes(search.toLowerCase()),
      )
    : emails

  // Auto-load more on scroll
  useEffect(() => {
    const el = loadMoreRef.current
    if (!el) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) {
          fetchNextPage()
        }
      },
      { rootMargin: '200px' }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  function toggleSelect(id: number, checked: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (checked) next.add(id)
      else next.delete(id)
      return next
    })
  }

  return (
    <div className="flex h-full">
      {/* Email list */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <div className="flex items-center gap-3 border-b border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-[#111827]">
          <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
            <Inbox className="h-4 w-4" />
            <span>Inbox</span>
            <span className="text-xs">({filtered.length}{total > filtered.length ? ` of ${total}` : ''})</span>
          </div>

          <div className="ml-auto flex items-center gap-2">
            {/* Search */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search inbox..."
                className="h-8 w-48 rounded-lg border border-gray-200 bg-gray-50 pl-8 pr-3 text-xs text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
              />
            </div>

            {/* Refresh */}
            <button
              onClick={() => refetch()}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300"
            >
              <RefreshCw className={cn('h-4 w-4', isFetching && 'animate-spin')} />
            </button>
          </div>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex h-64 items-center justify-center">
              <Spinner />
            </div>
          ) : isError ? (
            <EmptyState
              icon={Inbox}
              title="Failed to load inbox"
              description="Could not connect to the server. Make sure the backend is running."
              action={
                <button
                  onClick={() => refetch()}
                  className="mt-2 text-sm text-indigo-600 hover:text-indigo-700"
                >
                  Retry
                </button>
              }
            />
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={Inbox}
              title={search ? 'No emails match your search' : 'No inbox emails yet'}
              description={
                search
                  ? 'Try a different search term.'
                  : 'Inbound replies from recipients will appear here.'
              }
            />
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-800/80">
              {filtered.map((email) => (
                <EmailRow
                  key={email.id}
                  email={email}
                  isSelected={selectedIds.has(email.id)}
                  onSelect={toggleSelect}
                  onClick={() => setDetailEmail(email)}
                />
              ))}
            </div>
          )}

          {/* Load More sentinel — auto-triggers IntersectionObserver */}
          {!isLoading && !isError && hasNextPage && filtered.length > 0 && (
            <div ref={loadMoreRef} className="flex justify-center py-4">
              {isFetchingNextPage && (
                <div className="flex items-center gap-2 text-xs text-gray-400">
                  <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                  Loading more...
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Detail pane */}
      {detailEmail && (
        <EmailDetailPane
          email={detailEmail}
          onClose={() => setDetailEmail(null)}
        />
      )}
    </div>
  )
}
