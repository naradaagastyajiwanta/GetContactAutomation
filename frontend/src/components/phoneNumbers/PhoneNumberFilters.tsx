import { X } from 'lucide-react'
import { SearchInput } from '../ui/SearchInput'
import { Select } from '../ui/Select'
import { Button } from '../ui/Button'

interface PhoneNumberFiltersProps {
  search: string
  onSearchChange: (value: string) => void
  province: string
  onProvinceChange: (value: string) => void
  universitySearch: string
  onUniversitySearchChange: (value: string) => void
  sort: string
  onSortChange: (value: string) => void
  provinces?: string[]
  onClearFilters: () => void
}

export function PhoneNumberFilters({
  search,
  onSearchChange,
  province,
  onProvinceChange,
  universitySearch,
  onUniversitySearchChange,
  sort,
  onSortChange,
  provinces = [],
  onClearFilters,
}: PhoneNumberFiltersProps) {
  const hasActiveFilters = !!(search || province || universitySearch || sort)

  const provinceOptions = [
    { value: '', label: 'All Provinces' },
    ...provinces.map((p) => ({ value: p, label: p })),
  ]

  const sortOptions = [
    { value: '', label: 'Default (Newest)' },
    { value: 'phone_number_asc', label: 'Phone (A to Z)' },
    { value: 'phone_number_desc', label: 'Phone (Z to A)' },
    { value: 'university_asc', label: 'University (A to Z)' },
    { value: 'contact_name_asc', label: 'Contact Name (A to Z)' },
    { value: 'created_at_asc', label: 'Oldest First' },
    { value: 'created_at_desc', label: 'Newest First' },
  ]

  return (
    <div className="space-y-4 rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        {/* Search by phone or contact name */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Phone or Contact Name
          </label>
          <SearchInput
            placeholder="Search phone number..."
            value={search}
            onChange={onSearchChange}
          />
        </div>

        {/* Search by university */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            University
          </label>
          <SearchInput
            placeholder="Search university..."
            value={universitySearch}
            onChange={onUniversitySearchChange}
          />
        </div>

        {/* Province filter */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Province
          </label>
          <Select value={province} onChange={onProvinceChange} options={provinceOptions} />
        </div>

        {/* Sort */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Sort By
          </label>
          <Select value={sort} onChange={onSortChange} options={sortOptions} />
        </div>
      </div>

      {/* Clear filters button */}
      {hasActiveFilters && (
        <div className="flex justify-end">
          <Button
            variant="ghost"
            size="sm"
            onClick={onClearFilters}
            className="text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100"
          >
            <X className="h-4 w-4 mr-1" />
            Clear Filters
          </Button>
        </div>
      )}
    </div>
  )
}
