import { useRef, useState } from 'react'
import { Upload, FileSpreadsheet } from 'lucide-react'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { useImportUniversities } from '../../hooks/useUniversities'

interface ImportModalProps {
  isOpen: boolean
  onClose: () => void
}

export function ImportModal({ isOpen, onClose }: ImportModalProps) {
  const [file, setFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const importMutation = useImportUniversities()

  const handleSubmit = () => {
    if (!file) return
    importMutation.mutate(file, {
      onSuccess: () => {
        setFile(null)
        onClose()
      },
    })
  }

  const handleClose = () => {
    if (!importMutation.isPending) {
      setFile(null)
      onClose()
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Import Universities" size="lg">
      <div className="space-y-4">
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Upload a CSV or Excel (.xlsx) file. The system will auto-detect columns from the header row.
        </p>

        {/* Format guide */}
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-900">
          <div className="mb-2 flex items-center gap-2">
            <FileSpreadsheet className="h-4 w-4 text-gray-500 dark:text-gray-400" />
            <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">
              Format
            </span>
          </div>
          <div className="space-y-1.5 text-xs text-gray-600 dark:text-gray-400">
            <p>
              Baris pertama = header. Kolom yang dikenali:
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="pb-1 pr-4 font-semibold text-gray-700 dark:text-gray-300">Field</th>
                    <th className="pb-1 pr-4 font-semibold text-gray-700 dark:text-gray-300">Header yang diterima</th>
                    <th className="pb-1 font-semibold text-gray-700 dark:text-gray-300">Wajib?</th>
                  </tr>
                </thead>
                <tbody className="font-mono">
                  <tr>
                    <td className="py-0.5 pr-4">Nama</td>
                    <td className="py-0.5 pr-4">name, nama, university, institusi, perguruan tinggi</td>
                    <td className="py-0.5 font-sans font-medium text-red-600 dark:text-red-400">Ya</td>
                  </tr>
                  <tr>
                    <td className="py-0.5 pr-4">Provinsi</td>
                    <td className="py-0.5 pr-4">province, provinsi, prov</td>
                    <td className="py-0.5 font-sans text-gray-500">Tidak</td>
                  </tr>
                  <tr>
                    <td className="py-0.5 pr-4">Website</td>
                    <td className="py-0.5 pr-4">website, web, url, situs, laman</td>
                    <td className="py-0.5 font-sans text-gray-500">Tidak</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="pt-1 text-gray-500 dark:text-gray-500">
              Jika tidak ada header yang cocok, kolom pertama dianggap sebagai nama universitas.
            </p>
          </div>
        </div>

        <div
          className="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 p-8 transition-colors hover:border-indigo-400 dark:border-gray-600 dark:hover:border-indigo-500"
          onClick={() => fileInputRef.current?.click()}
        >
          <Upload className="mb-2 h-8 w-8 text-gray-400" />
          {file ? (
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
              {file.name}
            </p>
          ) : (
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Click to select a CSV or Excel file
            </p>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.xlsx"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
        </div>

        <div className="flex justify-end gap-3">
          <Button
            variant="secondary"
            onClick={handleClose}
            disabled={importMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!file}
            loading={importMutation.isPending}
          >
            Import
          </Button>
        </div>
      </div>
    </Modal>
  )
}
