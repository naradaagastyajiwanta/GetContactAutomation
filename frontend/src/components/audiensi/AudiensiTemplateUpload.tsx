import { useState, useRef, type ChangeEvent } from 'react'
import { Upload, FileText, CheckCircle } from 'lucide-react'
import { Card } from '../ui/Card'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../ui/Table'
import { uploadTemplate, getTemplatePlaceholders } from '../../api/audiensi'
import { useQuery } from '@tanstack/react-query'
import toast from 'react-hot-toast'

export function AudiensiTemplateUpload() {
  const [uploading, setUploading] = useState(false)
  const [uploaded, setUploaded] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data: placeholderData, isLoading: placeholdersLoading } = useQuery({
    queryKey: ['audiensi', 'template', 'placeholders'],
    queryFn: getTemplatePlaceholders,
  })

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null
    setSelectedFile(file)
    setUploaded(false)
  }

  const handleUpload = async () => {
    if (!selectedFile) {
      toast.error('Pilih file .docx terlebih dahulu')
      return
    }

    setUploading(true)
    try {
      await uploadTemplate(selectedFile)
      toast.success('Template berhasil diupload')
      setUploaded(true)
      setSelectedFile(null)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || 'Gagal upload template')
    } finally {
      setUploading(false)
    }
  }

  return (
    <Card>
      <div className="space-y-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          Surat Undangan Template
        </h2>

        {/* File Upload */}
        <div className="space-y-3">
          <div
            className="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 px-6 py-8 transition-colors hover:border-indigo-400 dark:border-gray-600 dark:hover:border-indigo-500"
            onClick={() => fileInputRef.current?.click()}
          >
            {selectedFile ? (
              <>
                <FileText className="mb-3 h-10 w-10 text-indigo-500 dark:text-indigo-400" />
                <p className="text-sm font-medium text-indigo-700 dark:text-indigo-300">
                  {selectedFile.name}
                </p>
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  {(selectedFile.size / 1024).toFixed(1)} KB — klik untuk ganti file
                </p>
              </>
            ) : (
              <>
                <Upload className="mb-3 h-10 w-10 text-gray-400 dark:text-gray-500" />
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  Klik untuk pilih file .docx
                </p>
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  Hanya file .docx yang diterima
                </p>
              </>
            )}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            className="hidden"
            onChange={handleFileChange}
          />
          <div className="flex items-center gap-3">
            <Button
              variant="primary"
              loading={uploading}
              disabled={!selectedFile}
              onClick={handleUpload}
            >
              <FileText className="h-4 w-4" />
              Upload Template
            </Button>
            {uploaded && (
              <span className="flex items-center gap-1.5 text-sm text-green-600 dark:text-green-400">
                <CheckCircle className="h-4 w-4" />
                Template berhasil diupload
              </span>
            )}
          </div>
        </div>

        {/* Available Placeholders */}
        <div>
          <h3 className="mb-3 text-sm font-semibold text-gray-900 dark:text-gray-100">
            Placeholder yang tersedia
          </h3>
          <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
            Tulis placeholder berikut di file .docx template Anda. Sistem akan otomatis menggantinya per universitas.
          </p>
          {placeholdersLoading ? (
            <div className="flex justify-center py-6">
              <Spinner size="md" />
            </div>
          ) : placeholderData?.placeholders && placeholderData.placeholders.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Placeholder</TableHead>
                  <TableHead>Keterangan</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {placeholderData.placeholders.map((p) => (
                  <TableRow key={p.key}>
                    <TableCell className="font-mono text-xs text-indigo-600 dark:text-indigo-400">
                      {p.key}
                    </TableCell>
                    <TableCell>{p.description}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Tidak ada placeholder tersedia.
            </p>
          )}
        </div>
      </div>
    </Card>
  )
}
