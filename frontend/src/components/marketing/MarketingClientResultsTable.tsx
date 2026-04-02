import { useState } from 'react'
import {
  CheckCircle2,
  Circle,
  Pencil,
  X,
  Plus,
  ChevronDown,
  ChevronUp,
  Trash2,
  Wifi,
  Mail,
  Phone,
  User,
  Briefcase,
  AlertTriangle,
  Instagram,
  ExternalLink,
  Image as ImageIcon,
  Clock3,
} from 'lucide-react'
import { cn } from '../../lib/utils'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { Badge } from '../ui/Badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/Table'
import {
  useUpdateMarketingContact,
  useDeleteMarketingClient,
  useAddMarketingClient,
} from '../../hooks/useMarketing'
import toast from 'react-hot-toast'
import type {
  MarketingClient,
  MarketingContact,
  ContactType,
  MarketingInstagramCandidate,
  MarketingInstagramPost,
} from '../../api/marketing'

const CONTACT_ICONS: Record<ContactType, React.ElementType> = {
  wa_phone: Wifi,
  email: Mail,
  office_phone: Phone,
  pic_name: User,
  pic_title: Briefcase,
}

const CONTACT_TYPE_OPTIONS = [
  { value: 'wa_phone', label: 'WA' },
  { value: 'email', label: 'Email' },
  { value: 'office_phone', label: 'Telp Kantor' },
  { value: 'pic_name', label: 'Nama PIC' },
  { value: 'pic_title', label: 'Jabatan PIC' },
]

const IG_SOURCE_LABELS: Record<string, string> = {
  website_social: 'Website Resmi',
  ig_web_search: 'IG Search',
  ddg_search: 'DDG',
}

function formatDateTime(date: string | null | undefined): string {
  if (!date) return '-'
  return new Intl.DateTimeFormat('id-ID', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(date))
}

function truncateText(value: string | null | undefined, maxLength = 180): string {
  if (!value) return ''
  if (value.length <= maxLength) return value
  return `${value.slice(0, maxLength).trimEnd()}...`
}

function getSelectedInstagramCandidates(client: MarketingClient): MarketingInstagramCandidate[] {
  return (client.ig_candidates ?? []).filter((candidate) => candidate.is_selected)
}

function getInstagramHandlesFromPosts(posts: MarketingInstagramPost[]): string[] {
  return Array.from(
    new Set(posts.map((post) => (post.ig_handle ?? '').trim()).filter(Boolean))
  )
}

function getVisibleInstagramHandles(client: MarketingClient): Array<{
  handle: string
  isPrimary: boolean
  source: 'candidate' | 'post' | 'profile'
}> {
  const selectedCandidates = getSelectedInstagramCandidates(client)
  if (selectedCandidates.length > 0) {
    return selectedCandidates.map((candidate) => ({
      handle: candidate.handle,
      isPrimary: candidate.is_primary,
      source: 'candidate',
    }))
  }

  const postHandles = getInstagramHandlesFromPosts(client.ig_posts ?? [])
  if (postHandles.length > 0) {
    const primaryHandle = (client.ig_handle ?? '').trim().toLowerCase()
    return postHandles.map((handle) => ({
      handle,
      isPrimary: handle.toLowerCase() === primaryHandle,
      source: 'post',
    }))
  }

  if (client.ig_handle) {
    return [{ handle: client.ig_handle, isPrimary: true, source: 'profile' }]
  }

  return []
}

type ClientDetailTab = 'contacts' | 'posts' | 'instagram'

function getInstagramCandidateStatus(candidate: {
  is_primary?: boolean
  is_selected?: boolean
  llm_is_correct?: boolean | null
}) {
  if (candidate.is_primary) {
    return {
      label: 'Primary',
      className: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
    }
  }
  if (candidate.is_selected) {
    return {
      label: 'Selected',
      className: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
    }
  }
  if (candidate.llm_is_correct === false) {
    return {
      label: 'Rejected',
      className: 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300',
    }
  }
  return {
    label: 'Observed',
    className: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  }
}

function MarketingInstagramAccountsPanel({ client }: { client: MarketingClient }) {
  const posts = client.ig_posts ?? []
  const candidates = client.ig_candidates ?? []
  const postHandleCounts = new Map<string, number>()

  for (const post of posts) {
    const handle = (post.ig_handle ?? '').trim().toLowerCase()
    if (!handle) continue
    postHandleCounts.set(handle, (postHandleCounts.get(handle) ?? 0) + 1)
  }

  const rows = candidates.length > 0
    ? candidates.map((candidate) => ({
        key: `candidate-${candidate.id}`,
        handle: candidate.handle,
        subtitle: candidate.full_name || candidate.external_domain || null,
        source: IG_SOURCE_LABELS[candidate.source ?? ''] ?? candidate.source ?? 'Unknown source',
        status: getInstagramCandidateStatus(candidate),
        score: candidate.final_score,
        posts: postHandleCounts.get(candidate.handle.toLowerCase()) ?? 0,
        href: candidate.profile_url || `https://instagram.com/${candidate.handle}`,
      }))
    : getVisibleInstagramHandles(client).map((account) => ({
        key: `${account.source}-${account.handle}`,
        handle: account.handle,
        subtitle: account.source === 'post' ? 'Derived from scraped posts' : 'Stored profile',
        source: account.source === 'post' ? 'IG Posts' : 'Stored profile',
        status: getInstagramCandidateStatus({ is_primary: account.isPrimary }),
        score: null,
        posts: postHandleCounts.get(account.handle.toLowerCase()) ?? 0,
        href: `https://instagram.com/${account.handle}`,
      }))

  if (rows.length === 0) {
    return (
      <div className="px-4 py-5 text-sm text-gray-500 dark:text-gray-400">
        Belum ada akun Instagram yang berhasil ditemukan.
      </div>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Handle</TableHead>
          <TableHead>Source</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Score</TableHead>
          <TableHead>Posts</TableHead>
          <TableHead>Link</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.key}>
            <TableCell>
              <div className="min-w-0">
                <div className="font-medium text-gray-900 dark:text-gray-100">@{row.handle}</div>
                {row.subtitle && (
                  <div className="truncate text-xs text-gray-500 dark:text-gray-400">{row.subtitle}</div>
                )}
              </div>
            </TableCell>
            <TableCell className="text-xs text-gray-500 dark:text-gray-400">{row.source}</TableCell>
            <TableCell>
              <Badge className={row.status.className}>{row.status.label}</Badge>
            </TableCell>
            <TableCell>{row.score != null ? `${Math.round(row.score * 100)}%` : '—'}</TableCell>
            <TableCell>{row.posts}</TableCell>
            <TableCell>
              <a
                href={row.href}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
              >
                Buka
                <ExternalLink className="h-3 w-3" />
              </a>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function MarketingInstagramPostsPanel({ posts }: { posts: MarketingInstagramPost[] }) {
  if (posts.length === 0) {
    return (
      <div className="px-4 py-5 text-sm text-gray-500 dark:text-gray-400">
        Belum ada post Instagram yang tersimpan.
      </div>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Image</TableHead>
          <TableHead>Account</TableHead>
          <TableHead>Caption</TableHead>
          <TableHead>Source</TableHead>
          <TableHead>Date</TableHead>
          <TableHead>Link</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {posts.map((post) => (
          <TableRow key={post.id}>
            <TableCell>
              {post.image_url ? (
                <img
                  src={post.image_url}
                  alt="Instagram post"
                  loading="lazy"
                  referrerPolicy="no-referrer"
                  className="h-12 w-12 rounded-md object-cover"
                />
              ) : (
                <div className="flex h-12 w-12 items-center justify-center rounded-md bg-gray-100 text-gray-400 dark:bg-gray-800 dark:text-gray-500">
                  <ImageIcon className="h-4 w-4" />
                </div>
              )}
            </TableCell>
            <TableCell>
              <div className="font-medium text-gray-900 dark:text-gray-100">
                @{post.ig_handle || 'unknown'}
              </div>
            </TableCell>
            <TableCell className="max-w-sm">
              <span className="block truncate">{truncateText(post.caption, 90) || 'Tanpa caption'}</span>
            </TableCell>
            <TableCell className="text-xs text-gray-500 dark:text-gray-400">{post.source || '—'}</TableCell>
            <TableCell>{formatDateTime(post.post_timestamp ?? post.created_at)}</TableCell>
            <TableCell>
              <a
                href={post.post_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
              >
                Buka
                <ExternalLink className="h-3 w-3" />
              </a>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function MarketingContactsPanel({
  client,
  groupId,
  onApprove,
  onEdit,
}: {
  client: MarketingClient
  groupId: number
  onApprove: (id: number, approved: boolean) => void
  onEdit: (id: number, value: string) => void
}) {
  const hasContacts = (client.contacts ?? []).length > 0

  if (!hasContacts) {
    return (
      <div className="p-4">
        <p className="mb-2 text-sm text-gray-500 dark:text-gray-400">Belum ada kontak</p>
        <EmptyClientState client={client} groupId={groupId} />
      </div>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Tipe</TableHead>
          <TableHead>Nilai</TableHead>
          <TableHead>Sumber</TableHead>
          <TableHead>Confidence</TableHead>
          <TableHead className="text-center">Approved</TableHead>
          <TableHead className="text-center">Selected</TableHead>
          <TableHead>Aksi</TableHead>
        </TableRow>
      </TableHeader>
      <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
        {client.contacts.map((contact) => (
          <ContactRow
            key={contact.id}
            contact={contact}
            onApprove={onApprove}
            onEdit={onEdit}
          />
        ))}
      </tbody>
    </Table>
  )
}

function InstagramDiscoveryPanel({ client }: { client: MarketingClient }) {
  const posts = client.ig_posts ?? []
  const candidates = client.ig_candidates ?? []
  const selectedCandidates = getSelectedInstagramCandidates(client)
  const visibleHandles = getVisibleInstagramHandles(client)
  const postHandles = getInstagramHandlesFromPosts(posts)
  const hasInstagramData = Boolean(client.ig_handle) || posts.length > 0 || candidates.length > 0

  if (!hasInstagramData) {
    return null
  }

  return (
    <div className="border-b border-indigo-100 bg-indigo-50/60 p-4 dark:border-indigo-900/60 dark:bg-indigo-950/20">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Instagram className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Instagram Discovery
            </p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {visibleHandles.length > 0
              ? visibleHandles.map((handle) => (
                  <span
                    key={`${handle.source}-${handle.handle}`}
                    className={cn(
                      'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold shadow-sm',
                      handle.isPrimary
                        ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
                        : 'bg-white text-indigo-700 dark:bg-gray-900 dark:text-indigo-300',
                    )}
                  >
                    @{handle.handle}
                    {handle.isPrimary ? ' · primary' : ''}
                  </span>
                ))
              : null}
          </div>
          <p className="text-xs text-gray-600 dark:text-gray-300">
            {candidates.length > 0
              ? `${candidates.length} kandidat IG dievaluasi, ${selectedCandidates.length} akun dipilih untuk scraping.`
              : postHandles.length > 1
                ? `${posts.length} post tersimpan dari ${postHandles.length} akun IG yang berhasil discrape.`
              : posts.length > 0
                ? `${posts.length} post tersimpan dari akun IG ini untuk audit flow pencarian.`
                : 'Handle IG sudah tersimpan, tapi belum ada post yang berhasil discrape.'}
          </p>
          {client.ig_last_scraped_at && (
            <div className="flex items-center gap-1 text-[11px] text-gray-500 dark:text-gray-400">
              <Clock3 className="h-3 w-3" />
              Last scrape {formatDateTime(client.ig_last_scraped_at)}
            </div>
          )}
        </div>

        {client.ig_profile_url && (
          <a
            href={client.ig_profile_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 self-start rounded-md border border-indigo-200 bg-white px-2.5 py-1 text-xs font-medium text-indigo-700 transition-colors hover:bg-indigo-100 dark:border-indigo-800 dark:bg-gray-900 dark:text-indigo-300 dark:hover:bg-indigo-900/40"
          >
            <ExternalLink className="h-3 w-3" />
            Buka Profil
          </a>
        )}
      </div>

      {candidates.length > 0 && (
        <div className="mt-4 space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">
              Candidate Ranking
            </p>
            <p className="text-[11px] text-gray-500 dark:text-gray-400">
              Primary + secondary account untuk corporate scrape
            </p>
          </div>
          <div className="grid gap-2 lg:grid-cols-2">
            {candidates.map((candidate) => (
              <InstagramCandidateCard key={candidate.id} candidate={candidate} />
            ))}
          </div>
        </div>
      )}

      {posts.length > 0 && (
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {posts.map((post) => (
            <InstagramPostCard key={post.id} post={post} />
          ))}
        </div>
      )}
    </div>
  )
}

function InstagramCandidateCard({ candidate }: { candidate: MarketingInstagramCandidate }) {
  const statusLabel = candidate.is_primary
    ? 'Primary'
    : candidate.is_selected
      ? 'Selected'
      : candidate.llm_is_correct === false
        ? 'Rejected'
        : 'Observed'

  const statusClassName = candidate.is_primary
    ? 'bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-300'
    : candidate.is_selected
      ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
      : candidate.llm_is_correct === false
        ? 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300'
        : 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300'

  return (
    <div className="rounded-xl border border-indigo-100 bg-white p-3 shadow-sm dark:border-gray-800 dark:bg-gray-900">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
              @{candidate.handle}
            </p>
            <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-semibold', statusClassName)}>
              {statusLabel}
            </span>
            {candidate.is_verified && (
              <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300">
                Verified
              </span>
            )}
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {IG_SOURCE_LABELS[candidate.source ?? ''] ?? candidate.source ?? 'Unknown source'}
            {candidate.rank_order ? ` · Rank ${candidate.rank_order}` : ''}
            {` · Score ${Math.round(candidate.final_score * 100)}%`}
          </p>
          <div className="flex flex-wrap gap-1 pt-1">
            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-700 dark:bg-gray-800 dark:text-gray-300">
              Affinity {Math.round(candidate.affinity_score * 100)}%
            </span>
            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-700 dark:bg-gray-800 dark:text-gray-300">
              Base {Math.round(candidate.base_score * 100)}%
            </span>
            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-700 dark:bg-gray-800 dark:text-gray-300">
              Profile {Math.round(candidate.profile_score * 100)}%
            </span>
            {candidate.llm_is_correct !== null && (
              <span
                className={cn(
                  'rounded-full px-2 py-0.5 text-[10px] font-medium',
                  candidate.llm_is_correct
                    ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                    : 'bg-rose-50 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300',
                )}
              >
                LLM {candidate.llm_is_correct ? 'Accept' : 'Reject'}
              </span>
            )}
          </div>
          {candidate.full_name && (
            <p className="text-xs font-medium text-gray-700 dark:text-gray-200">
              {candidate.full_name}
            </p>
          )}
        </div>

        {candidate.profile_url && (
          <a
            href={candidate.profile_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex flex-shrink-0 items-center gap-1 rounded-md border border-gray-200 px-2 py-1 text-[11px] font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800"
          >
            <ExternalLink className="h-3 w-3" />
            Buka
          </a>
        )}
      </div>

      {(candidate.bio || candidate.snippet || candidate.llm_reason) && (
        <div className="mt-3 space-y-2 text-xs text-gray-600 dark:text-gray-300">
          {(candidate.bio || candidate.snippet) && (
            <p>
              {truncateText(candidate.bio || candidate.snippet, 180)}
            </p>
          )}
          {candidate.llm_reason && (
            <p className="rounded-lg bg-gray-50 px-2.5 py-2 text-[11px] text-gray-600 dark:bg-gray-800/80 dark:text-gray-300">
              {candidate.llm_reason}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function InstagramPostCard({ post }: { post: MarketingInstagramPost }) {
  return (
    <div className="overflow-hidden rounded-xl border border-indigo-100 bg-white shadow-sm dark:border-gray-800 dark:bg-gray-900">
      {post.image_url ? (
        <a href={post.image_url} target="_blank" rel="noreferrer" className="block">
          <img
            src={post.image_url}
            alt="Instagram post"
            loading="lazy"
            referrerPolicy="no-referrer"
            className="h-44 w-full object-cover"
          />
        </a>
      ) : (
        <div className="flex h-44 items-center justify-center bg-gray-100 text-gray-400 dark:bg-gray-800 dark:text-gray-500">
          <ImageIcon className="h-8 w-8" />
        </div>
      )}

      <div className="space-y-3 p-3">
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400">
          {post.source && (
            <span className="rounded-full bg-gray-100 px-2 py-0.5 font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-300">
              {post.source}
            </span>
          )}
          <span>{formatDateTime(post.post_timestamp ?? post.created_at)}</span>
        </div>

        <p className="text-sm leading-5 text-gray-700 dark:text-gray-200">
          {truncateText(post.caption, 220) || 'Tanpa caption'}
        </p>

        <div className="flex flex-wrap items-center gap-2 text-xs font-medium">
          <a
            href={post.post_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 rounded-md border border-gray-200 px-2.5 py-1 text-gray-700 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800"
          >
            <ExternalLink className="h-3 w-3" />
            Buka Post
          </a>
          {post.image_url && (
            <a
              href={post.image_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 rounded-md border border-gray-200 px-2.5 py-1 text-gray-700 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800"
            >
              <ImageIcon className="h-3 w-3" />
              Buka Gambar
            </a>
          )}
        </div>
      </div>
    </div>
  )
}

function ContactRow({
  contact,
  onApprove,
  onEdit,
}: {
  contact: MarketingContact
  onApprove: (id: number, approved: boolean) => void
  onEdit: (id: number, value: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [editValue, setEditValue] = useState(contact.edited_value ?? contact.value ?? '')
  const Icon = CONTACT_ICONS[contact.contact_type] ?? Circle

  function commitEdit() {
    if (editValue !== (contact.edited_value ?? contact.value ?? '')) {
      onEdit(contact.id, editValue)
    }
    setEditing(false)
  }

  return (
    <tr className="border-t border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50">
      <td className="px-3 py-2">
        <div className="flex items-center gap-2">
          <Icon className="h-3.5 w-3.5 flex-shrink-0 text-gray-400" />
          <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
            {contact.contact_type}
          </span>
        </div>
      </td>
      <td className="px-3 py-2 min-w-0">
        {editing ? (
          <input
            autoFocus
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitEdit()
              if (e.key === 'Escape') { setEditing(false); setEditValue(contact.edited_value ?? contact.value ?? '') }
            }}
            className="w-full rounded border border-indigo-500 bg-white px-2 py-1 text-sm
              focus:outline-none focus:ring-1 focus:ring-indigo-500
              dark:border-indigo-400 dark:bg-gray-700 dark:text-gray-100"
          />
        ) : (
          <span
            className={cn(
              'text-sm',
              contact.edited_value
                ? 'text-indigo-700 dark:text-indigo-300 font-medium'
                : 'text-gray-900 dark:text-gray-100'
            )}
          >
            {contact.value ?? <span className="italic text-gray-400">—</span>}
          </span>
        )}
      </td>
      <td className="px-3 py-2 text-xs text-gray-500 dark:text-gray-400 max-w-32 truncate">
        {contact.source_url ?? contact.source_type ?? '—'}
      </td>
      <td className="px-3 py-2 text-xs text-gray-500 dark:text-gray-400">
        {contact.confidence != null ? `${Math.round(contact.confidence * 100)}%` : '—'}
      </td>
      <td className="px-3 py-2 text-center">
        <button
          type="button"
          onClick={() => onApprove(contact.id, !contact.is_approved)}
          className={cn(
            'transition-colors',
            contact.is_approved
              ? 'text-green-600 hover:text-green-700 dark:text-green-400'
              : 'text-gray-300 hover:text-green-600 dark:text-gray-600 dark:hover:text-green-400'
          )}
          title={contact.is_approved ? 'Batalkan approve' : 'Approve'}
        >
          {contact.is_approved
            ? <CheckCircle2 className="h-4 w-4" />
            : <Circle className="h-4 w-4" />}
        </button>
      </td>
      <td className="px-3 py-2 text-center">
        <span className="text-xs text-gray-400">
          {contact.is_approved ? '—' : 'Unchecked'}
        </span>
      </td>
      <td className="px-3 py-2">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setEditing((e) => !e)}
            className={cn(
              'rounded p-1 transition-colors',
              editing
                ? 'text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-900/30'
                : 'text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400'
            )}
            title="Edit nilai"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          {editing && (
            <>
              <button
                type="button"
                onClick={commitEdit}
                className="rounded p-1 text-green-600 hover:bg-green-50 dark:hover:bg-green-900/30"
                title="Simpan"
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => {
                  setEditing(false)
                  setEditValue(contact.edited_value ?? contact.value ?? '')
                }}
                className="rounded p-1 text-gray-400 hover:text-red-500"
                title="Batal"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </>
          )}
        </div>
      </td>
    </tr>
  )
}

function EmptyClientState({
  client,
  groupId,
}: {
  client: MarketingClient
  groupId: number
}) {
  const [show, setShow] = useState(false)
  const addClient = useAddMarketingClient()
  // For manual contact entry, we'd use a different endpoint.
  // Since there's no "add contact" endpoint in the API contract, we'll just note the not_found status.
  void addClient

  const isError = client.search_status === 'error'

  if (!show) {
    return (
      <div className="mt-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() => setShow(true)}
          className="text-xs"
        >
          <Plus className="h-3 w-3" />
          Tambah Kontak Manual
        </Button>
      </div>
    )
  }

  return (
    <div
      className={cn(
        'mt-2 flex items-start gap-2 rounded-lg border p-3',
        isError
          ? 'border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/40'
          : 'border-indigo-200 bg-indigo-50 dark:border-indigo-800 dark:bg-indigo-950'
      )}
    >
      {isError && <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-500" />}
      <span
        className={cn(
          'text-xs font-medium',
          isError
            ? 'text-red-700 dark:text-red-300'
            : 'text-indigo-700 dark:text-indigo-300'
        )}
      >
        {isError
          ? `Pencarian gagal: ${client.error_message ?? 'unknown error'}`
          : 'Kontak tidak ditemukan — silakan tambah manual setelah data ditemukan'}
      </span>
      <Button
        size="sm"
        variant="ghost"
        onClick={() => setShow(false)}
        className="ml-auto text-xs"
      >
        Tutup
      </Button>
    </div>
  )
}

function ClientCard({
  client,
  groupId,
  canManage,
}: {
  client: MarketingClient
  groupId: number
  canManage: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const [activeTab, setActiveTab] = useState<ClientDetailTab>('contacts')
  const updateContact = useUpdateMarketingContact()
  const deleteClient = useDeleteMarketingClient()

  function handleApprove(contactId: number, approved: boolean) {
    updateContact.mutate({ contactId, payload: { is_approved: approved } })
  }

  function handleEdit(contactId: number, value: string) {
    updateContact.mutate({ contactId, payload: { edited_value: value } })
  }

  function handleDelete() {
    if (!window.confirm('Hapus client ini?')) return
    deleteClient.mutate({ clientId: client.id, groupId })
  }

  const hasContacts = (client.contacts ?? []).length > 0
  const hasApproved = (client.contacts ?? []).some((c) => c.is_approved)
  const igCandidateCount = client.ig_candidates?.length ?? 0
  const igPostCount = client.ig_posts?.length ?? 0
  const visibleInstagramHandles = getVisibleInstagramHandles(client)
  const headerInstagramCandidates = visibleInstagramHandles.slice(0, 3)
  const remainingInstagramCandidateCount = Math.max(0, visibleInstagramHandles.length - headerInstagramCandidates.length)
  const tabs: Array<{ key: ClientDetailTab; label: string; count: number }> = [
    { key: 'contacts', label: 'Contacts', count: client.contacts?.length ?? 0 },
    { key: 'posts', label: 'Posts', count: client.ig_posts?.length ?? 0 },
    { key: 'instagram', label: 'IG Accounts', count: Math.max(client.ig_candidates?.length ?? 0, visibleInstagramHandles.length) },
  ]

  return (
    <Card padding={false} className="overflow-hidden">
      {/* Client header row */}
      <div
        className={cn(
          'flex items-center gap-3 px-4 py-3 cursor-pointer transition-colors',
          expanded
            ? 'bg-indigo-50 dark:bg-indigo-950/50'
            : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'
        )}
        onClick={() => setExpanded((e) => !e)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
              {client.name}
            </p>
            {client.search_status === 'not_found' && (
              <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-[10px] font-semibold text-red-600 dark:bg-red-900/30 dark:text-red-400">
                <X className="h-3 w-3" /> Tidak Ditemukan
              </span>
            )}
            {client.search_status === 'error' && (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                <AlertTriangle className="h-3 w-3" /> Error Search
              </span>
            )}
            {client.search_status === 'found' && (
              <span className="inline-flex items-center gap-1 rounded-full bg-green-50 px-2 py-0.5 text-[10px] font-semibold text-green-600 dark:bg-green-900/30 dark:text-green-400">
                <CheckCircle2 className="h-3 w-3" /> Ditemukan
              </span>
            )}
            {client.search_status === 'searching' && (
              <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-semibold text-blue-600 dark:bg-blue-900/30 dark:text-blue-400">
                Searching...
              </span>
            )}
          </div>

          {(headerInstagramCandidates.length > 0 || client.ig_handle || remainingInstagramCandidateCount > 0) && (
            <div className="mt-1 flex flex-wrap items-center gap-2">
            {headerInstagramCandidates.length > 0
              ? headerInstagramCandidates.map((candidate) => (
                  <span
                    key={`${candidate.source}-${candidate.handle}`}
                    className={cn(
                      'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold',
                      candidate.isPrimary
                        ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                        : 'bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300',
                    )}
                  >
                    <Instagram className="h-3 w-3" /> @{candidate.handle}
                  </span>
                ))
              : null}
            {remainingInstagramCandidateCount > 0 && (
              <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-semibold text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                +{remainingInstagramCandidateCount} IG
              </span>
            )}
            </div>
          )}
          <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            {hasContacts
              ? `${(client.contacts ?? []).length} kontak · ${(client.contacts ?? []).filter((c) => c.is_approved).length} approved`
              : 'Belum ada kontak'}
            {igCandidateCount > 0 ? ` · ${igCandidateCount} kandidat IG` : ''}
            {igPostCount > 0 ? ` · ${igPostCount} post IG` : ''}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {canManage && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                handleDelete()
              }}
              className="rounded p-1 text-gray-400 hover:text-red-500 transition-colors"
              title="Hapus client"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-gray-400" />
          ) : (
            <ChevronDown className="h-4 w-4 text-gray-400" />
          )}
        </div>
      </div>

      {/* Expanded contacts table */}
      {expanded && (
        <div className="border-t border-gray-200 dark:border-gray-700">
          <div className="border-b border-gray-200 px-4 dark:border-gray-700">
            <nav className="flex gap-4 overflow-x-auto">
              {tabs.map((tab) => (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setActiveTab(tab.key)}
                  className={cn(
                    'border-b-2 px-1 py-3 text-sm font-medium transition-colors whitespace-nowrap',
                    activeTab === tab.key
                      ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
                      : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300',
                  )}
                >
                  {tab.label}
                  <span className="ml-2 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-300">
                    {tab.count}
                  </span>
                </button>
              ))}
            </nav>
          </div>

          {activeTab === 'contacts' && (
            <MarketingContactsPanel
              client={client}
              groupId={groupId}
              onApprove={handleApprove}
              onEdit={handleEdit}
            />
          )}
          {activeTab === 'posts' && (
            <MarketingInstagramPostsPanel posts={client.ig_posts ?? []} />
          )}
          {activeTab === 'instagram' && (
            <MarketingInstagramAccountsPanel client={client} />
          )}
        </div>
      )}
    </Card>
  )
}

interface MarketingClientResultsTableProps {
  clients: MarketingClient[]
  groupId: number
  canManage: boolean
}

export function MarketingClientResultsTable({
  clients,
  groupId,
  canManage,
}: MarketingClientResultsTableProps) {
  if (clients.length === 0) {
    return (
      <div className="py-12 text-center text-sm text-gray-500 dark:text-gray-400">
        Belum ada client di group ini
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {clients.map((client) => (
        <ClientCard
          key={client.id}
          client={client}
          groupId={groupId}
          canManage={canManage}
        />
      ))}
    </div>
  )
}
