import { useState } from 'react'
import { Download, FileSpreadsheet } from 'lucide-react'
import toast from 'react-hot-toast'
import { downloadCsv } from '../../api/export'
import { Card } from '../ui/Card'
import { Button } from '../ui/Button'

export function ExportSection() {
  const [loading, setLoading] = useState(false)

  const handleExport = async () => {
    setLoading(true)
    try {
      await downloadCsv()
      toast.success('CSV downloaded successfully')
    } catch {
      toast.error('Failed to download CSV')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card padding={false}>
      <div className="flex items-center justify-between px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-100 dark:bg-emerald-900/30">
            <FileSpreadsheet className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">Export Data</p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Download all university data &amp; contacts as CSV
            </p>
          </div>
        </div>
        <Button variant="secondary" size="sm" loading={loading} onClick={handleExport}>
          <Download className="h-4 w-4" />
          Download CSV
        </Button>
      </div>
    </Card>
  )
}
