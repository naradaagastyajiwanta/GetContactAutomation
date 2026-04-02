/**
 * EmailImapSentView — shows raw emails from the IMAP Sent folder.
 */

import { useState, memo, useEffect, useRef } from 'react'
import {
  Send,
  RefreshCw,
  Search,
  Mail,
  ChevronRight,
} from 'lucide-react'
import { cn, formatRelative } from '../../lib/utils'
import { useSentFolderEmailsPaginated } from '../../hooks/useEmailBlast'
import type { EmailCacheRowId, SentFolderEmail } from '../../api/emailBlast'
import { Spinner } from '../ui/Spinner'
import { EmptyState } from '../ui/EmptyState'

const SentRow = memo(function SentRow({
  email,
  isSelected,
  onSelect,
  onClick,
}: {
  email: SentFolderEmail
  isSelected: boolean
  onSelect: (id: EmailCacheRowId, checked: boolean) => void
  onClick: () => void
}) {
  const bodyPreview = email.body?.replace(/<[^>]+>/g, '').slice(0, 80) ?? ''

  return (
    <div
      onClick={onClick}
      className={cn(
        'group flex cursor-pointer items-center gap-3 border-b border-gray-50 px-4 py-3 transition-colors hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/50',
        isSelected && 'bg-indigo-50 dark:bg-indigo-950/30',
      )}
    >
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

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              'truncate text-[13px] font-medium',
              isSelected ? 'text-indigo-700 dark:text-indigo-300' : 'text-gray-900 dark:text-gray-100',
            )}
          >
            To: {email.to_email || '(unknown)'}
          </span>
        </div>
        <div className="truncate text-[12px] text-gray-500 dark:text-gray-400">
          {email.subject ? `${email.subject} — ` : ''}{bodyPreview}
        </div>
        {email.mailbox_email && (
          <div className="mt-1 truncate text-[11px] text-gray-400 dark:text-gray-500">
            Mailbox: {email.mailbox_email}
          </div>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <span className="text-[11px] text-gray-400 dark:text-gray-500">
          {formatRelative(email.date)}
        </span>
        <ChevronRight className="h-4 w-4 text-gray-300 opacity-0 transition-opacity group-hover:opacity-100" />
      </div>
    </div>
  )
})

function SentDetailPane({
  email,
  onClose,
}: {
  email: SentFolderEmail | null
  onClose: () => void
}) {
  if (!email) return null

  return (
    <div className="flex h-full w-[480px] shrink-0 flex-col border-l border-gray-200 bg-white dark:border-gray-700 dark:bg-[#111827]">
      <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3 dark:border-gray-800">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">IMAP Sent Email</h3>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
        >
          ✕
        </button>
      </div>

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
            {email.mailbox_email && (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Mailbox: {email.mailbox_email}
              </p>
            )}
          </div>
        </div>

        <div className="mb-1 text-sm text-gray-700 dark:text-gray-200">
          <span className="font-medium">To: </span>
          {email.to_email || '(unknown)'}
        </div>
        <div className="mb-1 text-sm text-gray-700 dark:text-gray-200">
          <span className="font-medium">Subject: </span>
          {email.subject || '(no subject)'}
        </div>
        <div className="text-xs text-gray-400 dark:text-gray-500">
          {email.date
            ? new Date(email.date).toLocaleString('id-ID', {
                weekday: 'long',
                day: 'numeric',
                month: 'long',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
              })
            : '—'}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4">
        <div className="whitespace-pre-wrap text-sm leading-relaxed text-gray-700 dark:text-gray-200">
          {email.body || '(no content)'}
        </div>
      </div>
    </div>
  )
}

export function EmailImapSentView() {
  const [search, setSearch] = useState('')
  const [mailboxFilter, setMailboxFilter] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<EmailCacheRowId>>(new Set())
  const [detailEmail, setDetailEmail] = useState<SentFolderEmail | null>(null)
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
  } = useSentFolderEmailsPaginated(PAGE_SIZE)

  const emails: SentFolderEmail[] = data?.pages.flatMap((page) => (page.emails as SentFolderEmail[]) ?? []) ?? []
  const total = data?.pages[0]?.total ?? 0
  const mailboxOptions = Array.from(new Set(emails.map((email) => (email.mailbox_email ?? '').trim()).filter(Boolean))).sort()

  const searchValue = search.toLowerCase()
  const filtered = emails.filter((email) => {
    const matchesMailbox = !mailboxFilter || (email.mailbox_email ?? '') === mailboxFilter
    if (!matchesMailbox) {
      return false
    }

    if (!search.trim()) {
      return true
    }

    return (
      (email.to_email ?? '').toLowerCase().includes(searchValue) ||
      (email.from_email ?? '').toLowerCase().includes(searchValue) ||
      (email.from_name ?? '').toLowerCase().includes(searchValue) ||
      (email.subject ?? '').toLowerCase().includes(searchValue) ||
      (email.body ?? '').toLowerCase().includes(searchValue)
    )
  })

  useEffect(() => {
    const el = loadMoreRef.current
    if (!el) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) {
          fetchNextPage()
        }
      },
      { rootMargin: '200px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  function toggleSelect(id: EmailCacheRowId, checked: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (checked) next.add(id)
      else next.delete(id)
      return next
    })
  }

  return (
    <div className="flex h-full">
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="flex items-center gap-3 border-b border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-[#111827]">
          <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
            <Send className="h-4 w-4" />
            <span>Sent IMAP</span>
            <span className="text-xs">
              ({filtered.length}
              {total > filtered.length ? ` of ${total}` : ''})
            </span>
          </div>

          <div className="ml-auto flex items-center gap-2">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Cari email IMAP..."
                className="h-8 w-48 rounded-lg border border-gray-200 bg-gray-50 pl-8 pr-3 text-xs text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
              />
            </div>

            <select
              value={mailboxFilter}
              onChange={(event) => setMailboxFilter(event.target.value)}
              className="h-8 rounded-lg border border-gray-200 bg-gray-50 px-2.5 text-xs text-gray-900 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
            >
              <option value="">Semua mailbox</option>
              {mailboxOptions.map((mailbox) => (
                <option key={mailbox} value={mailbox}>{mailbox}</option>
              ))}
            </select>

            <button
              onClick={() => refetch()}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300"
            >
              <RefreshCw className={cn('h-4 w-4', isFetching && 'animate-spin')} />
            </button>
          </div>
        </div>

        <div className="border-b border-gray-100 bg-gray-50/80 px-4 py-2.5 text-[11px] text-gray-500 dark:border-gray-800 dark:bg-gray-900/40 dark:text-gray-400">
          Folder mentah dari mailbox. Cocok untuk inspeksi email aktual, tetapi tidak selalu punya attribution campaign.
        </div>

        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex h-64 items-center justify-center">
              <Spinner />
            </div>
          ) : isError ? (
            <EmptyState
              icon={Send}
              title="Failed to load IMAP sent emails"
              description="Could not connect to the server."
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
              icon={Send}
              title={search ? 'Tidak ada email IMAP yang cocok' : 'Belum ada email IMAP terkirim'}
              description={
                search
                  ? 'Coba kata kunci lain.'
                  : 'Email mentah dari folder Sent mailbox akan muncul di sini.'
              }
            />
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-800/80">
              {filtered.map((email) => (
                <SentRow
                  key={email.id}
                  email={email}
                  isSelected={selectedIds.has(email.id)}
                  onSelect={toggleSelect}
                  onClick={() => setDetailEmail(email)}
                />
              ))}
            </div>
          )}

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

      {detailEmail && (
        <SentDetailPane email={detailEmail} onClose={() => setDetailEmail(null)} />
      )}
    </div>
  )
}