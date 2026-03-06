import { useState } from 'react'
import { CheckCircle, Clock, ExternalLink, Image, ListChecks, Megaphone, MessageCircle, Phone, User, X, XCircle } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../ui/Table'
import { EmptyState } from '../ui/EmptyState'
import { Button } from '../ui/Button'
import { formatDate } from '../../lib/utils'
import { useToggleContactContacted } from '../../hooks/useUniversities'
import { queryKeys } from '../../lib/queryKeys'
import { BulkUpdateContactsModal } from './BulkUpdateContactsModal'
import { AddToBlastModal } from '../blast/AddToBlastModal'
import type { IgContact } from '../../lib/types'

function ContactStatusBadge({
  contact,
  onToggle,
  isToggling,
}: {
  contact: IgContact
  onToggle: (contacted: boolean) => void
  isToggling: boolean
}) {
  const state = contact.conversation_state
  const manualContacted = contact.manual_contacted

  // Has a real conversation → show conversation state (not toggleable)
  if (state) {
    const upper = state.toUpperCase()

    if (['GOT_NUMBER', 'COMPLETED'].includes(upper)) {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400">
          <CheckCircle className="h-3 w-3" />
          Berhasil
        </span>
      )
    }

    if (['REFUSED', 'ABANDONED'].includes(upper)) {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-700 dark:bg-red-900/30 dark:text-red-400">
          <XCircle className="h-3 w-3" />
          {upper === 'REFUSED' ? 'Ditolak' : 'Abandoned'}
        </span>
      )
    }

    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
        <MessageCircle className="h-3 w-3" />
        {upper === 'PENDING' ? 'Pending' : 'Sedang dihubungi'}
      </span>
    )
  }

  // No conversation → toggleable manual status
  if (manualContacted) {
    return (
      <button
        onClick={() => onToggle(false)}
        disabled={isToggling}
        className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400 hover:bg-green-200 dark:hover:bg-green-900/50 transition-colors cursor-pointer disabled:opacity-50"
        title="Klik untuk tandai belum dihubungi"
      >
        <CheckCircle className="h-3 w-3" />
        Sudah dihubungi
      </button>
    )
  }

  return (
    <button
      onClick={() => onToggle(true)}
      disabled={isToggling}
      className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors cursor-pointer disabled:opacity-50"
      title="Klik untuk tandai sudah dihubungi"
    >
      <Clock className="h-3 w-3" />
      Belum dihubungi
    </button>
  )
}

interface ContactsPanelProps {
  contacts: IgContact[]
  universityId: number
}

export function ContactsPanel({ contacts, universityId }: ContactsPanelProps) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [bulkOpen, setBulkOpen] = useState(false)
  const [blastOpen, setBlastOpen] = useState(false)
  const queryClient = useQueryClient()
  const toggleMutation = useToggleContactContacted(universityId)

  const contactIds = contacts.map((c) => c.id)

  const handleBulkUpdated = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.universities.contacts(universityId) })
  }

  if (contacts.length === 0) {
    return (
      <>
        <div className="mb-3 flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={() => setBlastOpen(true)}>
            <Megaphone className="h-4 w-4" />
            Add to Blast
          </Button>
          <Button variant="secondary" size="sm" onClick={() => setBulkOpen(true)}>
            <ListChecks className="h-4 w-4" />
            Bulk Update Status
          </Button>
        </div>
        <EmptyState
          icon={Phone}
          title="No contacts found"
          description="No phone contacts have been extracted for this university yet."
        />
        <BulkUpdateContactsModal
          isOpen={bulkOpen}
          onClose={() => setBulkOpen(false)}
          onUpdated={handleBulkUpdated}
        />
        <AddToBlastModal
          isOpen={blastOpen}
          onClose={() => setBlastOpen(false)}
          universityIds={[universityId]}
          label={`All contacts from this university`}
        />
      </>
    )
  }

  return (
    <>
      <div className="mb-3 flex justify-end gap-2">
        <Button variant="secondary" size="sm" onClick={() => setBlastOpen(true)} disabled={contacts.length === 0}>
          <Megaphone className="h-4 w-4" />
          Add to Blast
        </Button>
        <Button variant="secondary" size="sm" onClick={() => setBulkOpen(true)}>
          <ListChecks className="h-4 w-4" />
          Bulk Update Status
        </Button>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Source</TableHead>
            <TableHead>Name</TableHead>
            <TableHead>Phone Number</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Post</TableHead>
            <TableHead>Found At</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {contacts.map((contact) => (
            <TableRow key={contact.id}>
              <TableCell>
                {contact.source_image_url ? (
                  <img
                    src={contact.source_image_url}
                    alt="Source"
                    className="h-12 w-12 rounded object-cover cursor-pointer hover:opacity-80 transition-opacity"
                    onClick={() => setPreviewUrl(contact.source_image_url)}
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = 'none'
                    }}
                  />
                ) : (
                  <div className="h-12 w-12 rounded bg-gray-100 dark:bg-gray-700 flex items-center justify-center">
                    <Image className="h-5 w-5 text-gray-400" />
                  </div>
                )}
              </TableCell>
              <TableCell>
                <div className="flex items-center gap-1.5">
                  {contact.has_person_name ? (
                    <User className="h-3.5 w-3.5 text-green-500 shrink-0" />
                  ) : (
                    <User className="h-3.5 w-3.5 text-gray-300 dark:text-gray-600 shrink-0" />
                  )}
                  <span>{contact.contact_name || '-'}</span>
                </div>
              </TableCell>
              <TableCell className="font-mono">{contact.phone_number}</TableCell>
              <TableCell>
                <ContactStatusBadge
                  contact={contact}
                  onToggle={(contacted) =>
                    toggleMutation.mutate({ contactId: contact.id, contacted })
                  }
                  isToggling={toggleMutation.isPending}
                />
              </TableCell>
              <TableCell>
                {contact.source_post_url ? (
                  <a
                    href={contact.source_post_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
                  >
                    View Post
                    <ExternalLink className="h-3 w-3" />
                  </a>
                ) : (
                  '-'
                )}
              </TableCell>
              <TableCell>{formatDate(contact.created_at)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {/* Image preview modal */}
      {previewUrl && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
          onClick={() => setPreviewUrl(null)}
        >
          <div className="relative max-h-[90vh] max-w-[90vw]">
            <button
              onClick={() => setPreviewUrl(null)}
              className="absolute -top-3 -right-3 rounded-full bg-white dark:bg-gray-800 p-1 shadow-lg hover:bg-gray-100 dark:hover:bg-gray-700"
            >
              <X className="h-5 w-5" />
            </button>
            <img
              src={previewUrl}
              alt="Source preview"
              className="max-h-[85vh] max-w-[85vw] rounded-lg object-contain"
            />
          </div>
        </div>
      )}

      {/* Bulk update modal */}
      <BulkUpdateContactsModal
        isOpen={bulkOpen}
        onClose={() => setBulkOpen(false)}
        onUpdated={handleBulkUpdated}
      />

      <AddToBlastModal
        isOpen={blastOpen}
        onClose={() => setBlastOpen(false)}
        contactIds={contactIds}
        label={`${contacts.length} contacts from this university`}
      />
    </>
  )
}
