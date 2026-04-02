import { useState } from 'react'
import { Send, Wifi, Mail, CheckCircle2 } from 'lucide-react'
import { Card } from '../ui/Card'
import { Button } from '../ui/Button'
import { MarketingHandoffModal } from './MarketingHandoffModal'
import type { MarketingContact } from '../../api/marketing'

function groupContactsByType(contacts: MarketingContact[]) {
  const wa = contacts.filter(
    (c) => c.is_approved && c.is_selected && c.contact_type === 'wa_phone'
  )
  const email = contacts.filter(
    (c) => c.is_approved && c.is_selected && c.contact_type === 'email'
  )
  return { wa, email }
}

interface MarketingReadyToBlastPanelProps {
  clients: { contacts: MarketingContact[] }[]
  groupId: number
}

export function MarketingReadyToBlastPanel({ clients, groupId }: MarketingReadyToBlastPanelProps) {
  const [handoffOpen, setHandoffOpen] = useState(false)

  const allContacts = clients.flatMap((c) => c.contacts)
  const { wa, email } = groupContactsByType(allContacts)

  const approvedSelectedContacts = allContacts.filter(
    (c) => c.is_approved && c.is_selected
  )

  if (approvedSelectedContacts.length === 0) {
    return (
      <Card className="border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-50 dark:bg-indigo-900/30">
              <Send className="h-4 w-4 text-indigo-500" />
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                Siap Dikirim
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                0 kontak siap di-blast
              </p>
            </div>
          </div>
          <span className="rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-400 dark:bg-gray-800 dark:text-gray-500">
            0 WA · 0 Email
          </span>
        </div>
        <p className="mt-3 text-xs text-gray-400 dark:text-gray-500">
          Approve dan select kontak untuk melihat mereka di panel ini
        </p>
      </Card>
    )
  }

  return (
    <>
      <Card className="border border-indigo-200 dark:border-indigo-800 bg-indigo-50/50 dark:bg-indigo-950/30">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-100 dark:bg-indigo-900/50">
              <Send className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                Siap Dikirim
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {approvedSelectedContacts.length} kontak dipilih untuk di-blast
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="flex items-center gap-1 rounded-full bg-green-100 px-2.5 py-1 text-xs font-semibold text-green-700 dark:bg-green-900/50 dark:text-green-400">
                <Wifi className="h-3 w-3" />
                {wa.length} WA
              </span>
              <span className="flex items-center gap-1 rounded-full bg-blue-100 px-2.5 py-1 text-xs font-semibold text-blue-700 dark:bg-blue-900/50 dark:text-blue-400">
                <Mail className="h-3 w-3" />
                {email.length} Email
              </span>
            </div>
            <Button size="sm" onClick={() => setHandoffOpen(true)}>
              <Send className="h-3.5 w-3.5" />
              Kirim ke Blast
            </Button>
          </div>
        </div>
      </Card>

      {handoffOpen && (
        <MarketingHandoffModal
          groupId={groupId}
          waCount={wa.length}
          emailCount={email.length}
          onClose={() => setHandoffOpen(false)}
        />
      )}
    </>
  )
}
