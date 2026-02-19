import { useState } from 'react'
import { Download } from 'lucide-react'
import toast from 'react-hot-toast'
import { downloadCsv } from '../../api/export'
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card'
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
    <Card>
      <CardHeader>
        <CardTitle>Export Data</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-4 text-sm text-gray-500 dark:text-gray-400">
          Download all university data and contact information as a CSV file.
        </p>
        <Button variant="secondary" loading={loading} onClick={handleExport}>
          <Download className="h-4 w-4" />
          Download CSV
        </Button>
      </CardContent>
    </Card>
  )
}
