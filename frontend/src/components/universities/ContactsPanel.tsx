import { ExternalLink, Phone } from 'lucide-react'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../ui/Table'
import { EmptyState } from '../ui/EmptyState'
import { formatDate } from '../../lib/utils'
import type { IgContact } from '../../lib/types'

interface ContactsPanelProps {
  contacts: IgContact[]
}

export function ContactsPanel({ contacts }: ContactsPanelProps) {
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
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Phone Number</TableHead>
          <TableHead>Source Post</TableHead>
          <TableHead>Found At</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {contacts.map((contact) => (
          <TableRow key={contact.id}>
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
  )
}
