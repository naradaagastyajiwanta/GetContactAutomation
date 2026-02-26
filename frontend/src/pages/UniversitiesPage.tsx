import { useState, useEffect } from 'react'
import { Upload, Building2, Plus, Download, ClipboardList, RefreshCw } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { useUniversities } from '../hooks/useUniversities'
import { exportUniversitiesExcel } from '../api/universities'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Spinner } from '../components/ui/Spinner'
import { Pagination } from '../components/ui/Pagination'
import { EmptyState } from '../components/ui/EmptyState'
import { UniversityFilters } from '../components/universities/UniversityFilters'
import { UniversityTable } from '../components/universities/UniversityTable'
import { RunningAgentsBanner } from '../components/universities/RunningAgentsBanner'
import { ImportModal } from '../components/universities/ImportModal'
import { AddUniversityModal } from '../components/universities/AddUniversityModal'
import { BulkSelectModal } from '../components/universities/BulkSelectModal'
import { ITEMS_PER_PAGE } from '../lib/constants'

export default function UniversitiesPage() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [province, setProvince] = useState('')
  const [hasIg, setHasIg] = useState('')
  const [enabledFilter, setEnabledFilter] = useState('')
  const [page, setPage] = useState(1)
  const [importOpen, setImportOpen] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [bulkSelectOpen, setBulkSelectOpen] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date())
  const [isAutoRefreshing, setIsAutoRefreshing] = useState(true)

  const params = {
    search: search || undefined,
    status: status || undefined,
    province: province || undefined,
    has_ig: hasIg === 'yes' ? true : hasIg === 'no' ? false : undefined,
    enabled: enabledFilter === 'yes' ? true : enabledFilter === 'no' ? false : undefined,
    limit: ITEMS_PER_PAGE,
    offset: (page - 1) * ITEMS_PER_PAGE,
  }

  const { data: result, isLoading, isFetching, refetch } = useUniversities(params, isAutoRefreshing)

  // Track last update time
  useEffect(() => {
    if (isFetching && !isLoading) {
      setLastUpdated(new Date())
    }
  }, [isFetching, isLoading])

  const universities = result?.data ?? []
  const total = result?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / ITEMS_PER_PAGE))

  const handleSearchChange = (value: string) => {
    setSearch(value)
    setPage(1)
  }

  const handleStatusChange = (value: string) => {
    setStatus(value)
    setPage(1)
  }

  const handleProvinceChange = (value: string) => {
    setProvince(value)
    setPage(1)
  }

  const handleHasIgChange = (value: string) => {
    setHasIg(value)
    setPage(1)
  }

  const handleEnabledChange = (value: string) => {
    setEnabledFilter(value)
    setPage(1)
  }

  const handleExport = () => {
    if (selected.size > 0) {
      exportUniversitiesExcel({ ids: Array.from(selected) })
    } else {
      exportUniversitiesExcel({
        search: search || undefined,
        status: status || undefined,
        province: province || undefined,
        has_ig: hasIg === 'yes' ? true : hasIg === 'no' ? false : undefined,
        enabled: enabledFilter === 'yes' ? true : enabledFilter === 'no' ? false : undefined,
      })
    }
  }

  const from = total === 0 ? 0 : (page - 1) * ITEMS_PER_PAGE + 1
  const to = Math.min(page * ITEMS_PER_PAGE, total)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          Universities
        </h1>
        <div className="flex items-center gap-2">
          <Button onClick={() => setAddOpen(true)}>
            <Plus className="h-4 w-4" />
            Add University
          </Button>
          <Button variant="secondary" onClick={() => setBulkSelectOpen(true)}>
            <ClipboardList className="h-4 w-4" />
            Bulk Select
          </Button>
          <Button variant="secondary" onClick={handleExport}>
            <Download className="h-4 w-4" />
            {selected.size > 0 ? `Export Contacts (${selected.size})` : 'Export All Contacts'}
          </Button>
          <Button variant="secondary" onClick={() => setImportOpen(true)}>
            <Upload className="h-4 w-4" />
            Import CSV/Excel
          </Button>
        </div>
      </div>

      <UniversityFilters
        search={search}
        onSearchChange={handleSearchChange}
        status={status}
        onStatusChange={handleStatusChange}
        province={province}
        onProvinceChange={handleProvinceChange}
        hasIg={hasIg}
        onHasIgChange={handleHasIgChange}
        enabled={enabledFilter}
        onEnabledChange={handleEnabledChange}
      />

      {/* Running agents indicator */}
      <RunningAgentsBanner />

      {/* Summary bar with auto-refresh indicator */}
      <div className="flex items-center justify-between text-sm text-gray-500 dark:text-gray-400">
        <span>
          {total > 0
            ? `Showing ${from.toLocaleString()}–${to.toLocaleString()} of ${total.toLocaleString()} universities`
            : 'No universities found'}
        </span>
        <div className="flex items-center gap-3">
          {/* Auto-refresh indicator */}
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => refetch()}
              className="rounded p-1 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700 transition-colors"
              title="Manually refresh"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setIsAutoRefreshing(!isAutoRefreshing)}
              className={`flex items-center gap-1 rounded px-2 py-0.5 text-xs transition-colors ${
                isAutoRefreshing
                  ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600'
              }`}
              title={isAutoRefreshing ? 'Auto-refresh on (30s)' : 'Auto-refresh off'}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${
                isAutoRefreshing ? 'bg-emerald-500' : 'bg-gray-400'
              }`}></span>
              <span>{isAutoRefreshing ? 'Auto' : 'Off'}</span>
            </button>
            {isFetching && !isLoading ? (
              <span className="flex items-center gap-1 text-xs text-gray-500">
                <Spinner size="sm" /> Updating…
              </span>
            ) : (
              <span className="text-xs text-gray-400">
                Updated {formatDistanceToNow(lastUpdated)}
              </span>
            )}
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <Spinner size="lg" />
        </div>
      ) : universities.length === 0 ? (
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
            <UniversityTable
              universities={universities}
              selected={selected}
              onSelectedChange={setSelected}
            />
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
      <AddUniversityModal isOpen={addOpen} onClose={() => setAddOpen(false)} />
      <BulkSelectModal
        isOpen={bulkSelectOpen}
        onClose={() => setBulkSelectOpen(false)}
        currentSelected={selected}
        onSelect={setSelected}
      />
    </div>
  )
}
