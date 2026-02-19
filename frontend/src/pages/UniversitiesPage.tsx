import { useState } from 'react'
import { Upload, Building2 } from 'lucide-react'
import { useUniversities } from '../hooks/useUniversities'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Spinner } from '../components/ui/Spinner'
import { Pagination } from '../components/ui/Pagination'
import { EmptyState } from '../components/ui/EmptyState'
import { UniversityFilters } from '../components/universities/UniversityFilters'
import { UniversityTable } from '../components/universities/UniversityTable'
import { ImportModal } from '../components/universities/ImportModal'
import { ITEMS_PER_PAGE } from '../lib/constants'

export default function UniversitiesPage() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [importOpen, setImportOpen] = useState(false)

  const params = {
    search: search || undefined,
    status: status || undefined,
    limit: ITEMS_PER_PAGE,
    offset: (page - 1) * ITEMS_PER_PAGE,
  }

  const { data: universities, isLoading } = useUniversities(params)

  const handleSearchChange = (value: string) => {
    setSearch(value)
    setPage(1)
  }

  const handleStatusChange = (value: string) => {
    setStatus(value)
    setPage(1)
  }

  const totalPages = universities
    ? Math.max(Math.ceil(universities.length < ITEMS_PER_PAGE ? page : (page + 1)), page)
    : 1

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          Universities
        </h1>
        <Button onClick={() => setImportOpen(true)}>
          <Upload className="h-4 w-4" />
          Import CSV
        </Button>
      </div>

      <UniversityFilters
        search={search}
        onSearchChange={handleSearchChange}
        status={status}
        onStatusChange={handleStatusChange}
      />

      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <Spinner size="lg" />
        </div>
      ) : !universities || universities.length === 0 ? (
        <Card>
          <EmptyState
            icon={Building2}
            title="No universities found"
            description="Try adjusting your filters or import universities from a CSV file."
            action={
              <Button onClick={() => setImportOpen(true)} size="sm">
                <Upload className="h-4 w-4" />
                Import CSV
              </Button>
            }
          />
        </Card>
      ) : (
        <>
          <Card padding={false}>
            <UniversityTable universities={universities} />
          </Card>
          <div className="flex justify-center">
            <Pagination
              currentPage={page}
              totalPages={totalPages}
              onPageChange={setPage}
            />
          </div>
        </>
      )}

      <ImportModal isOpen={importOpen} onClose={() => setImportOpen(false)} />
    </div>
  )
}
