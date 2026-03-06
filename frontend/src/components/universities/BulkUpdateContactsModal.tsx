import { useState } from 'react'
import { ClipboardPaste, Search, CheckCircle2, AlertCircle, CheckCircle, Clock } from 'lucide-react'
import toast from 'react-hot-toast'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { Badge } from '../ui/Badge'
import { bulkMatchContacts, bulkUpdateContactStatus, type BulkMatchedContact } from '../../api/universities'

interface BulkUpdateContactsModalProps {
  isOpen: boolean
  onClose: () => void
  onUpdated: () => void
}

function CurrentStatusBadge({ contact }: { contact: BulkMatchedContact }) {
  const state = contact.conversation_state
  if (state) {
    const upper = state.toUpperCase()
    if (['GOT_NUMBER', 'COMPLETED'].includes(upper)) {
      return <Badge className="bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">Berhasil</Badge>
    }
    if (['REFUSED', 'ABANDONED'].includes(upper)) {
      return <Badge className="bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400">Ditolak</Badge>
    }
    return <Badge className="bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">Sedang dihubungi</Badge>
  }
  if (contact.manual_contacted) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-green-700 dark:text-green-400">
        <CheckCircle className="h-3 w-3" /> Sudah dihubungi
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
      <Clock className="h-3 w-3" /> Belum dihubungi
    </span>
  )
}

export function BulkUpdateContactsModal({ isOpen, onClose, onUpdated }: BulkUpdateContactsModalProps) {
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [updating, setUpdating] = useState(false)
  const [matches, setMatches] = useState<BulkMatchedContact[] | null>(null)
  const [checkedIds, setCheckedIds] = useState<Set<number>>(new Set())
  const [notMatched, setNotMatched] = useState<string[]>([])
  const [targetStatus, setTargetStatus] = useState<boolean>(true) // true = sudah, false = belum

  const reset = () => {
    setText('')
    setMatches(null)
    setCheckedIds(new Set())
    setNotMatched([])
    setTargetStatus(true)
  }

  const handleClose = () => {
    if (!loading && !updating) {
      reset()
      onClose()
    }
  }

  const handleMatch = async () => {
    const lines = text
      .split(/[\n,;]+/)
      .map((l) => l.trim())
      .filter(Boolean)

    if (lines.length === 0) {
      toast.error('Paste minimal satu nomor telepon')
      return
    }

    setLoading(true)
    try {
      const result = await bulkMatchContacts(lines)
      setMatches(result.matched)
      // Check all matched by default
      setCheckedIds(new Set(result.matched.map((m) => m.id)))
      setNotMatched(result.not_matched)

      if (result.matched.length === 0) {
        toast.error('Tidak ada nomor yang cocok di database')
      }
    } catch {
      toast.error('Gagal mencari nomor kontak')
    } finally {
      setLoading(false)
    }
  }

  const toggleCheck = (id: number) => {
    setCheckedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    if (!matches) return
    if (checkedIds.size === matches.length) {
      setCheckedIds(new Set())
    } else {
      setCheckedIds(new Set(matches.map((m) => m.id)))
    }
  }

  const handleApply = async () => {
    if (checkedIds.size === 0) return

    setUpdating(true)
    try {
      const result = await bulkUpdateContactStatus(Array.from(checkedIds), targetStatus)
      toast.success(
        `${result.updated} kontak ditandai "${targetStatus ? 'Sudah dihubungi' : 'Belum dihubungi'}"`
      )
      onUpdated()
      handleClose()
    } catch {
      toast.error('Gagal mengupdate status kontak')
    } finally {
      setUpdating(false)
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Bulk Update Status Kontak" size="lg">
      <div className="space-y-4">
        {!matches ? (
          /* Step 1: Paste phone numbers */
          <>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Paste nomor telepon di bawah (satu per baris, atau dipisahkan koma/titik koma).
              Sistem akan mencocokkan dengan database kontak yang ada.
            </p>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={`08123456789\n628234567890\n+628345678901\n...`}
              rows={10}
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-mono text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
            />
            <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
              <span>
                {text.split(/[\n,;]+/).filter((l) => l.trim()).length} nomor terdeteksi
              </span>
              <button
                onClick={async () => {
                  try {
                    const clip = await navigator.clipboard.readText()
                    setText(clip)
                    toast.success('Berhasil paste dari clipboard')
                  } catch {
                    toast.error('Tidak bisa membaca clipboard')
                  }
                }}
                className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
              >
                <ClipboardPaste className="h-3.5 w-3.5" />
                Paste dari clipboard
              </button>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={handleClose}>
                Batal
              </Button>
              <Button onClick={handleMatch} loading={loading} disabled={!text.trim()}>
                <Search className="h-4 w-4" />
                Cek Nomor
              </Button>
            </div>
          </>
        ) : (
          /* Step 2: Review matches + pick status */
          <>
            <div className="flex items-center gap-3 text-sm">
              <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
                <CheckCircle2 className="h-4 w-4" />
                {matches.length} cocok
              </span>
              {notMatched.length > 0 && (
                <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400">
                  <AlertCircle className="h-4 w-4" />
                  {notMatched.length} tidak ditemukan
                </span>
              )}
            </div>

            {/* Target status selector */}
            <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-800/50">
              <p className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                Ubah status menjadi:
              </p>
              <div className="flex gap-3">
                <label
                  className={`flex cursor-pointer items-center gap-2 rounded-lg border px-4 py-2 text-sm transition-colors ${
                    targetStatus
                      ? 'border-green-500 bg-green-50 text-green-700 dark:border-green-600 dark:bg-green-900/30 dark:text-green-400'
                      : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700'
                  }`}
                >
                  <input
                    type="radio"
                    name="targetStatus"
                    checked={targetStatus === true}
                    onChange={() => setTargetStatus(true)}
                    className="text-green-600 focus:ring-green-500"
                  />
                  <CheckCircle className="h-4 w-4" />
                  Sudah dihubungi
                </label>
                <label
                  className={`flex cursor-pointer items-center gap-2 rounded-lg border px-4 py-2 text-sm transition-colors ${
                    !targetStatus
                      ? 'border-gray-500 bg-gray-100 text-gray-700 dark:border-gray-500 dark:bg-gray-700 dark:text-gray-300'
                      : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700'
                  }`}
                >
                  <input
                    type="radio"
                    name="targetStatus"
                    checked={targetStatus === false}
                    onChange={() => setTargetStatus(false)}
                    className="text-gray-600 focus:ring-gray-500"
                  />
                  <Clock className="h-4 w-4" />
                  Belum dihubungi
                </label>
              </div>
            </div>

            {/* Matched results table */}
            {matches.length > 0 && (
              <div className="max-h-72 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-gray-50 dark:bg-gray-800">
                    <tr>
                      <th className="w-10 px-3 py-2">
                        <input
                          type="checkbox"
                          checked={checkedIds.size === matches.length && matches.length > 0}
                          onChange={toggleAll}
                          className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                        />
                      </th>
                      <th className="px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300">Nomor</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300">Nama</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300">Universitas</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300">Status Saat Ini</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                    {matches.map((m) => (
                      <tr
                        key={m.id}
                        className={`cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 ${
                          checkedIds.has(m.id) ? '' : 'opacity-50'
                        }`}
                        onClick={() => toggleCheck(m.id)}
                      >
                        <td className="px-3 py-1.5">
                          <input
                            type="checkbox"
                            checked={checkedIds.has(m.id)}
                            onChange={() => toggleCheck(m.id)}
                            className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                          />
                        </td>
                        <td className="px-3 py-1.5 font-mono text-gray-900 dark:text-gray-100">
                          {m.phone_number}
                        </td>
                        <td className="px-3 py-1.5 text-gray-700 dark:text-gray-300">
                          {m.contact_name || '-'}
                        </td>
                        <td className="px-3 py-1.5">
                          <span className="text-gray-900 dark:text-gray-100">{m.university_name || '-'}</span>
                        </td>
                        <td className="px-3 py-1.5">
                          <CurrentStatusBadge contact={m} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Not matched numbers */}
            {notMatched.length > 0 && (
              <details className="rounded-lg border border-amber-200 bg-amber-50/50 px-3 py-2 dark:border-amber-800 dark:bg-amber-950/20">
                <summary className="cursor-pointer text-sm font-medium text-amber-700 dark:text-amber-400">
                  {notMatched.length} nomor tidak ditemukan
                </summary>
                <ul className="mt-1 space-y-0.5 text-xs font-mono text-amber-600 dark:text-amber-500">
                  {notMatched.map((num, i) => (
                    <li key={i}>• {num}</li>
                  ))}
                </ul>
              </details>
            )}

            <div className="flex items-center justify-between">
              <button
                onClick={() => { setMatches(null); setNotMatched([]) }}
                className="text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              >
                ← Kembali
              </button>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={handleClose}>
                  Batal
                </Button>
                <Button onClick={handleApply} loading={updating} disabled={checkedIds.size === 0}>
                  <CheckCircle2 className="h-4 w-4" />
                  Update {checkedIds.size} Kontak
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </Modal>
  )
}
