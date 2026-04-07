import { useState } from 'react'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { Select } from '../ui/Select'
import { useCreateMarketingGroup } from '../../hooks/useMarketing'
import toast from 'react-hot-toast'
import type { ClientType } from '../../api/marketing'

// Options use snake_case values (matching API), labels are for display
const CLIENT_TYPE_OPTIONS = [
  { value: 'lembaga_negara', label: 'Lembaga Negara' },
  { value: 'kementerian', label: 'Kementerian' },
  { value: 'bumn', label: 'BUMN' },
  { value: 'swasta_besar', label: 'Perusahaan Swasta Besar' },
  { value: 'asosiasi', label: 'Asosiasi' },
  { value: 'lpk', label: 'LPK' },
  { value: 'lkp', label: 'LKP' },
]

interface MarketingCreateGroupModalProps {
  onClose: () => void
}

export function MarketingCreateGroupModal({ onClose }: MarketingCreateGroupModalProps) {
  const [name, setName] = useState('')
  const [clientType, setClientType] = useState<ClientType>('lembaga_negara')

  const createMutation = useCreateMarketingGroup()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    try {
      await createMutation.mutateAsync({ name: name.trim(), client_type: clientType })
      toast.success('Group berhasil dibuat')
      onClose()
    } catch {
      toast.error('Gagal membuat group')
    }
  }

  const loading = createMutation.isPending

  return (
    <Modal isOpen onClose={onClose} title="Buat Group Baru" size="md">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
            Nama Group *
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Contoh: Kementerian 2025"
            autoFocus
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm
              focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500
              dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
            Tipe Client *
          </label>
          <Select
            value={clientType}
            onChange={(v) => setClientType(v as ClientType)}
            options={CLIENT_TYPE_OPTIONS}
            className="w-full"
          />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={loading}>
            Batal
          </Button>
          <Button type="submit" loading={loading} disabled={!name.trim()}>
            Buat Group
          </Button>
        </div>
      </form>
    </Modal>
  )
}
