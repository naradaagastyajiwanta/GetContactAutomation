import { useState, useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { RefreshCw, Download } from 'lucide-react'
import { usePhoneNumbers, usePhoneNumberStats } from '../hooks/usePhoneNumbers'
import { getProvinces } from '../api/universities'
import { Button } from '../components/ui/Button'
import { Spinner } from '../components/ui/Spinner'
import { Pagination } from '../components/ui/Pagination'
import { PhoneNumberStatsCard } from '../components/phoneNumbers/PhoneNumberStats'
import { PhoneNumberFilters } from '../components/phoneNumbers/PhoneNumberFilters'
import { PhoneNumberTable } from '../components/phoneNumbers/PhoneNumberTable'
import { ITEMS_PER_PAGE } from '../lib/constants'

export default function PhoneNumbersPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [provinces, setProvinces] = useState<string[]>([])

  // Initialize state from URL params
  const initialSearch = searchParams.get('search') || ''
  const initialProvince = searchParams.get('province') || ''
  const initialUniversity = searchParams.get('university') || ''
  const initialSort = searchParams.get('sort') || ''
  const initialPage = Math.max(1, parseInt(searchParams.get('page') || '1'))

  const [search, setSearch] = useState(initialSearch)
  const [province, setProvince] = useState(initialProvince)
  const [universitySearch, setUniversitySearch] = useState(initialUniversity)
  const [sort, setSort] = useState(initialSort)
  const [page, setPage] = useState(initialPage)

  // Load provinces on mount
  useEffect(() => {
    const loadProvinces = async () => {
      try {
        const data = await getProvinces()
        setProvinces(data)
      } catch (err) {
        console.error('Failed to load provinces:', err)
      }
    }
    loadProvinces()
  }, [])

  // Helper to update URL params
  const updateUrlParams = (updates: Record<string, string | null | number>) => {
    const newParams = new URLSearchParams(searchParams)

    Object.entries(updates).forEach(([key, value]) => {
      if (value === null || value === '') {
        newParams.delete(key)
      } else if (key === 'page' && value === 1) {
        newParams.delete('page')
      } else {
        newParams.set(key, String(value))
      }
    })

    setSearchParams(newParams)
  }

  // Check if any filters are active
  const hasActiveFilters = useMemo(() => {
    return !!(search || province || universitySearch || sort)
  }, [search, province, universitySearch, sort])

  // Clear all filters
  const clearFilters = () => {
    setSearch('')
    setProvince('')
    setUniversitySearch('')
    setSort('')
    setPage(1)
    setSearchParams({})
  }

  const params = {
    search: search || undefined,
    province: province || undefined,
    university_search: universitySearch || undefined,
    limit: ITEMS_PER_PAGE,
    offset: (page - 1) * ITEMS_PER_PAGE,
    sort_by: sort ? sort.replace(/_desc$|_asc$/, '') : undefined,
    order: sort?.endsWith('_desc')
      ? 'desc'
      : sort?.endsWith('_asc')
        ? 'asc'
        : undefined,
  }

  const {
    data: result,
    isLoading,
    isFetching,
    refetch,
  } = usePhoneNumbers(params)

  const { data: stats, isLoading: isStatsLoading } = usePhoneNumberStats()

  const phoneNumbers = result?.data ?? []
  const total = result?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / ITEMS_PER_PAGE))

  const handleSearchChange = (value: string) => {
    setSearch(value)
    setPage(1)
    updateUrlParams({ search: value || null, page: 1 })
  }

  const handleProvinceChange = (value: string) => {
    setProvince(value)
    setPage(1)
    updateUrlParams({ province: value || null, page: 1 })
  }

  const handleUniversitySearchChange = (value: string) => {
    setUniversitySearch(value)
    setPage(1)
    updateUrlParams({ university: value || null, page: 1 })
  }

  const handleSortChange = (value: string) => {
    setSort(value)
    setPage(1)
    updateUrlParams({ sort: value || null, page: 1 })
  }

  const handlePageChange = (newPage: number) => {
    setPage(newPage)
    updateUrlParams({ page: newPage })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleExport = () => {
    const phoneList = phoneNumbers.map((p) => p.phone_number).join('\n')
    const blob = new Blob([phoneList], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `phone-numbers-${new Date().toISOString().split('T')[0]}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  const from = total === 0 ? 0 : (page - 1) * ITEMS_PER_PAGE + 1
  const to = Math.min(page * ITEMS_PER_PAGE, total)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          Phone Numbers
        </h1>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          {phoneNumbers.length > 0 && (
            <Button variant="secondary" onClick={handleExport}>
              <Download className="h-4 w-4" />
              Export ({phoneNumbers.length})
            </Button>
          )}
        </div>
      </div>

      {/* Stats Card */}
      <PhoneNumberStatsCard stats={stats} isLoading={isStatsLoading} />

      {/* Filters */}
      <PhoneNumberFilters
        search={search}
        onSearchChange={handleSearchChange}
        province={province}
        onProvinceChange={handleProvinceChange}
        universitySearch={universitySearch}
        onUniversitySearchChange={handleUniversitySearchChange}
        sort={sort}
        onSortChange={handleSortChange}
        provinces={provinces}
        onClearFilters={clearFilters}
      />

      {/* Active filters bar */}
      {hasActiveFilters && (
        <div className="flex items-center justify-between rounded-lg bg-indigo-50 px-4 py-2 dark:bg-indigo-950/30">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium text-indigo-700 dark:text-indigo-300">
              Active filters:
            </span>
            {search && (
              <span className="rounded-full bg-white px-2 py-0.5 text-xs text-gray-700 dark:bg-gray-700 dark:text-gray-200">
                Phone: "{search}"
              </span>
            )}
            {universitySearch && (
              <span className="rounded-full bg-white px-2 py-0.5 text-xs text-gray-700 dark:bg-gray-700 dark:text-gray-200">
                University: "{universitySearch}"
              </span>
            )}
            {province && (
              <span className="rounded-full bg-white px-2 py-0.5 text-xs text-gray-700 dark:bg-gray-700 dark:text-gray-200">
                Province: {province}
              </span>
            )}
            {sort && (
              <span className="rounded-full bg-white px-2 py-0.5 text-xs text-gray-700 dark:bg-gray-700 dark:text-gray-200">
                Sort: {sort}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Table */}
      <div>
        <PhoneNumberTable data={phoneNumbers} isLoading={isLoading} />

        {/* Pagination info */}
        {total > 0 && (
          <div className="mt-4 flex items-center justify-between text-sm text-gray-600 dark:text-gray-400">
            <span>
              Showing {from} to {to} of {total} phone numbers
            </span>
            <Pagination
              currentPage={page}
              totalPages={totalPages}
              onPageChange={handlePageChange}
            />
          </div>
        )}
      </div>
    </div>
  )
}
