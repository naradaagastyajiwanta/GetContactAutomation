import { useState, useRef } from 'react'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { useImportPreview, useImportCommit } from '../../hooks/useMarketing'
import { Upload, FileSpreadsheet, CheckCircle2, AlertCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import type { ImportPreview } from '../../api/marketing'

interface MarketingImportModalProps {
  groupId: number
  onClose: () => void
}

export function MarketingImportModal({ groupId, onClose }: MarketingImportModalProps) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [commitDone, setCommitDone] = useState(false)
  const [commitResult, setCommitResult] = useState<{
    inserted: number
    skipped: number
    duplicates: number
  } | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isDragging, setIsDragging] = useState(false)

  const previewMutation = useImportPreview()
  const commitMutation = useImportCommit()

  function handleFileChange(f: File) {
    const ext = f.name.split('.').pop()?.toLowerCase()
    if (!['xlsx', 'csv'].includes(ext ?? '')) {
      toast.error('Format file harus .xlsx atau .csv')
      return
    }
    setFile(f)
    setPreview(null)
    setCommitDone(false)
    setCommitResult(null)
  }

  async function handleUpload() {
    if (!file) return
    try {
      const result = await previewMutation.mutateAsync({ groupId, file })
      setPreview(result)
    } catch {
      toast.error('Gagal membaca file')
    }
  }

  async function handleCommit() {
    if (!file) return
    try {
      const result = await commitMutation.mutateAsync({ groupId, file })
      setCommitDone(true)
      setCommitResult(result)
      toast.success(
        `${result.inserted} client ditambahkan`
      )
    } catch {
      toast.error('Gagal mengimpor data')
    }
  }

  const loading = previewMutation.isPending || commitMutation.isPending

  function handleClose() {
    if (commitDone) {
      onClose()
      return
    }
    onClose()
  }

  function renderStep1() {
    return (
      <div className="space-y-4">
        {/* Drop zone */}
        <div
          className={`relative cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
            isDragging
              ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950'
              : 'border-gray-300 dark:border-gray-600 hover:border-indigo-400 dark:hover:border-indigo-500'
          }`}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setIsDragging(false)
            const f = e.dataTransfer.files[0]
            if (f) handleFileChange(f)
          }}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.csv"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) handleFileChange(f)
            }}
          />
          <Upload className="mx-auto mb-3 h-8 w-8 text-gray-400" />
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {file ? file.name : 'Seret file ke sini, atau klik untuk pilih'}
          </p>
          <p className="mt-1 text-xs text-gray-400">Format: .xlsx atau .csv</p>
        </div>

        {file && (
          <div className="flex items-center gap-3 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 dark:border-gray-700 dark:bg-gray-800">
            <FileSpreadsheet className="h-5 w-5 flex-shrink-0 text-indigo-500" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                {file.name}
              </p>
              <p className="text-xs text-gray-500">{(file.size / 1024).toFixed(1)} KB</p>
            </div>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                setFile(null)
              }}
              className="text-xs text-gray-400 hover:text-red-500"
            >
              Hapus
            </button>
          </div>
        )}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Batal
          </Button>
          <Button
            onClick={handleUpload}
            loading={loading}
            disabled={!file}
          >
            <Upload className="h-4 w-4" />
            Upload & Preview
          </Button>
        </div>
      </div>
    )
  }

  function renderStep2() {
    if (!preview) return renderStep1()
    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-green-200 bg-green-50 p-3 dark:border-green-800 dark:bg-green-950">
          <p className="text-sm font-medium text-green-800 dark:text-green-200">
            File berhasil dibaca — {preview.total_rows} baris terdeteksi
          </p>
        </div>

        {/* Columns detected */}
        <div>
          <p className="mb-2 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
            Kolom Terdeteksi
          </p>
          <div className="flex flex-wrap gap-2">
            {(preview.columns ?? []).map((col: string) => (
              <span
                key={col}
                className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-300"
              >
                {col}
              </span>
            ))}
          </div>
        </div>

        {/* Preview table */}
        <div className="max-h-60 overflow-auto rounded-lg border border-gray-200 dark:border-gray-700">
          <table className="min-w-full text-xs">
            <thead className="bg-gray-50 dark:bg-gray-800/50 sticky top-0">
              <tr>
                {(preview.columns ?? []).map((col: string) => (
                  <th
                    key={col}
                    className="px-3 py-2 text-left font-medium text-gray-500 dark:text-gray-400 whitespace-nowrap"
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {(preview.rows ?? []).map((row: Record<string, string>, i: number) => (
                <tr key={i}>
                  {(preview.columns ?? []).map((col: string) => (
                    <td
                      key={col}
                      className="px-3 py-2 text-gray-700 dark:text-gray-300 whitespace-nowrap truncate max-w-xs"
                    >
                      {row[col] ?? '—'}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {(preview.duplicates ?? 0) > 0 && (
          <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-800 dark:bg-amber-950">
            <AlertCircle className="h-4 w-4 flex-shrink-0 text-amber-600" />
            <p className="text-xs text-amber-700 dark:text-amber-300">
              {preview.duplicates} baris merupakan duplikat dan akan dilewati saat import
            </p>
          </div>
        )}

        <div className="flex justify-between gap-2">
          <Button
            type="button"
            variant="secondary"
            onClick={() => { setPreview(null); setFile(null) }}
            disabled={loading}
          >
            Ganti File
          </Button>
          <Button
            onClick={handleCommit}
            loading={loading}
          >
            <CheckCircle2 className="h-4 w-4" />
            Commit Import
          </Button>
        </div>
      </div>
    )
  }

  function renderStep3() {
    return (
      <div className="space-y-4 py-4 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/50">
          <CheckCircle2 className="h-6 w-6 text-green-600 dark:text-green-400" />
        </div>
        <div>
          <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Import Berhasil
          </p>
          {commitResult && (
            <div className="mt-3 flex justify-center gap-6 text-sm">
              <div className="text-center">
                <p className="text-2xl font-bold text-green-600">{commitResult.inserted}</p>
                <p className="text-gray-500 dark:text-gray-400">Ditambahkan</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-gray-400">{commitResult.skipped}</p>
                <p className="text-gray-500 dark:text-gray-400">Dilewati</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-amber-500">{commitResult.duplicates}</p>
                <p className="text-gray-500 dark:text-gray-400">Duplikat</p>
              </div>
            </div>
          )}
        </div>
        <Button onClick={onClose} className="mt-2">
          Tutup
        </Button>
      </div>
    )
  }

  return (
    <Modal isOpen onClose={handleClose} title="Import Client dari Excel" size="lg">
      {commitDone ? renderStep3() : preview ? renderStep2() : renderStep1()}
    </Modal>
  )
}
