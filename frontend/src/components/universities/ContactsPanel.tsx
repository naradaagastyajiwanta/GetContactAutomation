import { useState } from 'react'
import { ExternalLink, Image, Phone, User, X } from 'lucide-react'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../ui/Table'
import { EmptyState } from '../ui/EmptyState'
import { formatDate } from '../../lib/utils'
import type { IgContact } from '../../lib/types'

interface ContactsPanelProps {
  contacts: IgContact[]
}

export function ContactsPanel({ contacts }: ContactsPanelProps) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)

  if (contacts.length === 0) {
    return (
      <EmptyState
        icon={Phone}
        title="No contacts found"
        description="No phone contacts have been extracted for this university yet."
      />
    )
  }

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Source</TableHead>
            <TableHead>Name</TableHead>
            <TableHead>Phone Number</TableHead>
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
    </>
  )
}
