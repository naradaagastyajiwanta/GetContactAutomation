import { useRef, useState } from 'react'
import { Upload } from 'lucide-react'
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
    <Modal isOpen={isOpen} onClose={handleClose} title="Import Universities">
      <div className="space-y-4">
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Upload a CSV file with university data. The file should contain columns
          for name, province, and other university details.
        </p>

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
              Click to select a CSV file
            </p>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
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
