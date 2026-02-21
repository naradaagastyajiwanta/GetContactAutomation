import { useState, type KeyboardEvent } from 'react'
import { Plus, Trash2, ClipboardList, PenLine } from 'lucide-react'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { useCreateUniversities } from '../../hooks/useUniversities'

interface AddUniversityModalProps {
  isOpen: boolean
  onClose: () => void
}

interface UniversityEntry {
  name: string
  province?: string
  website?: string
}

const PROVINCES = [
  'Aceh', 'Sumatera Utara', 'Sumatera Barat', 'Riau', 'Jambi',
  'Sumatera Selatan', 'Bengkulu', 'Lampung', 'Kepulauan Bangka Belitung',
  'Kepulauan Riau', 'DKI Jakarta', 'Jawa Barat', 'Jawa Tengah',
  'DI Yogyakarta', 'Jawa Timur', 'Banten', 'Bali', 'Nusa Tenggara Barat',
  'Nusa Tenggara Timur', 'Kalimantan Barat', 'Kalimantan Tengah',
  'Kalimantan Selatan', 'Kalimantan Timur', 'Kalimantan Utara',
  'Sulawesi Utara', 'Sulawesi Tengah', 'Sulawesi Selatan',
  'Sulawesi Tenggara', 'Gorontalo', 'Sulawesi Barat', 'Maluku',
  'Maluku Utara', 'Papua', 'Papua Barat', 'Papua Selatan', 'Papua Tengah',
  'Papua Pegunungan', 'Papua Barat Daya',
]

export function AddUniversityModal({ isOpen, onClose }: AddUniversityModalProps) {
  const [tab, setTab] = useState<'manual' | 'bulk'>('manual')

  // Manual tab state
  const [name, setName] = useState('')
  const [province, setProvince] = useState('')
  const [website, setWebsite] = useState('')
  const [entries, setEntries] = useState<UniversityEntry[]>([])

  // Bulk tab state
  const [bulkText, setBulkText] = useState('')
  const [bulkProvince, setBulkProvince] = useState('')

  const createMutation = useCreateUniversities()

  const resetForm = () => {
    setName('')
    setProvince('')
    setWebsite('')
    setEntries([])
    setBulkText('')
    setBulkProvince('')
  }

  const handleClose = () => {
    if (!createMutation.isPending) {
      resetForm()
      onClose()
    }
  }

  const addToList = () => {
    const trimmed = name.trim()
    if (!trimmed) return
    setEntries((prev) => [
      ...prev,
      {
        name: trimmed,
        province: province || undefined,
        website: website.trim() || undefined,
      },
    ])
    setName('')
    setWebsite('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      addToList()
    }
  }

  const removeEntry = (index: number) => {
    setEntries((prev) => prev.filter((_, i) => i !== index))
  }

  const handleSaveAll = () => {
    if (entries.length === 0) return
    createMutation.mutate(entries, {
      onSuccess: () => {
        resetForm()
        onClose()
      },
    })
  }

  const parseBulkLines = (): UniversityEntry[] => {
    return bulkText
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line.length > 0)
      .map((line) => ({
        name: line,
        province: bulkProvince || undefined,
      }))
  }

  const bulkEntries = parseBulkLines()

  const handleBulkImport = () => {
    if (bulkEntries.length === 0) return
    createMutation.mutate(bulkEntries, {
      onSuccess: () => {
        resetForm()
        onClose()
      },
    })
  }

  const inputClass =
    'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 dark:placeholder-gray-500 dark:focus:border-indigo-400 dark:focus:ring-indigo-400'

  const selectClass =
    'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 dark:focus:border-indigo-400 dark:focus:ring-indigo-400'

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Add Universities" size="lg">
      <div className="space-y-4">
        {/* Tab switcher */}
        <div className="flex border-b border-gray-200 dark:border-gray-700">
          <button
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium transition-colors ${
              tab === 'manual'
                ? 'border-b-2 border-indigo-500 text-indigo-600 dark:text-indigo-400'
                : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
            }`}
            onClick={() => setTab('manual')}
          >
            <PenLine className="h-4 w-4" />
            Input Manual
          </button>
          <button
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium transition-colors ${
              tab === 'bulk'
                ? 'border-b-2 border-indigo-500 text-indigo-600 dark:text-indigo-400'
                : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
            }`}
            onClick={() => setTab('bulk')}
          >
            <ClipboardList className="h-4 w-4" />
            Paste Bulk
          </button>
        </div>

        {/* Manual Tab */}
        {tab === 'manual' && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">
                  Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  className={inputClass}
                  placeholder="University name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  onKeyDown={handleKeyDown}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">
                  Province
                </label>
                <select
                  className={selectClass}
                  value={province}
                  onChange={(e) => setProvince(e.target.value)}
                >
                  <option value="">-- Select Province --</option>
                  {PROVINCES.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">
                  Website
                </label>
                <input
                  type="text"
                  className={inputClass}
                  placeholder="https://example.ac.id"
                  value={website}
                  onChange={(e) => setWebsite(e.target.value)}
                  onKeyDown={handleKeyDown}
                />
              </div>
            </div>

            <Button size="sm" variant="secondary" onClick={addToList} disabled={!name.trim()}>
              <Plus className="h-4 w-4" />
              Tambah ke Daftar
            </Button>

            {entries.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
                  {entries.length} university{entries.length > 1 ? ' entries' : ''} in list
                </p>
                <div className="max-h-48 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700">
                  {entries.map((entry, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between border-b border-gray-100 px-3 py-2 last:border-b-0 dark:border-gray-700"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-gray-900 dark:text-gray-100">
                          {entry.name}
                        </p>
                        <p className="truncate text-xs text-gray-500 dark:text-gray-400">
                          {[entry.province, entry.website].filter(Boolean).join(' | ') || 'No details'}
                        </p>
                      </div>
                      <button
                        onClick={() => removeEntry(i)}
                        className="ml-2 rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/20 dark:hover:text-red-400"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="flex justify-end gap-3">
              <Button variant="secondary" onClick={handleClose} disabled={createMutation.isPending}>
                Cancel
              </Button>
              <Button
                onClick={handleSaveAll}
                disabled={entries.length === 0}
                loading={createMutation.isPending}
              >
                Simpan Semua ({entries.length})
              </Button>
            </div>
          </div>
        )}

        {/* Bulk Tab */}
        {tab === 'bulk' && (
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">
                Paste university names (one per line)
              </label>
              <textarea
                className={`${inputClass} h-40 resize-none`}
                placeholder={"Universitas Indonesia\nUniversitas Gadjah Mada\nInstitut Teknologi Bandung"}
                value={bulkText}
                onChange={(e) => setBulkText(e.target.value)}
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">
                Province (applied to all)
              </label>
              <select
                className={selectClass}
                value={bulkProvince}
                onChange={(e) => setBulkProvince(e.target.value)}
              >
                <option value="">-- Select Province --</option>
                {PROVINCES.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>

            {bulkEntries.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
                  Preview: {bulkEntries.length} universit{bulkEntries.length > 1 ? 'ies' : 'y'}
                </p>
                <div className="max-h-36 overflow-y-auto rounded-lg border border-gray-200 bg-gray-50 p-2 dark:border-gray-700 dark:bg-gray-900">
                  {bulkEntries.map((entry, i) => (
                    <p key={i} className="truncate text-sm text-gray-700 dark:text-gray-300">
                      {i + 1}. {entry.name}
                    </p>
                  ))}
                </div>
              </div>
            )}

            <div className="flex justify-end gap-3">
              <Button variant="secondary" onClick={handleClose} disabled={createMutation.isPending}>
                Cancel
              </Button>
              <Button
                onClick={handleBulkImport}
                disabled={bulkEntries.length === 0}
                loading={createMutation.isPending}
              >
                Import ({bulkEntries.length})
              </Button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}
