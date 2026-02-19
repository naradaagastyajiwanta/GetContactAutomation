import { SearchInput } from '../ui/SearchInput'
import { Select } from '../ui/Select'

const statusOptions = [
  { value: '', label: 'All Statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'ig_found', label: 'IG Found' },
  { value: 'ig_scraped', label: 'Scraped' },
  { value: 'contacted', label: 'Contacted' },
  { value: 'got_number', label: 'Got Number' },
  { value: 'failed', label: 'Failed' },
]

interface UniversityFiltersProps {
  search: string
  onSearchChange: (value: string) => void
  status: string
  onStatusChange: (value: string) => void
}

export function UniversityFilters({
  search,
  onSearchChange,
  status,
  onStatusChange,
}: UniversityFiltersProps) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row">
      <SearchInput
        value={search}
        onChange={onSearchChange}
        placeholder="Search universities..."
        className="flex-1"
      />
      <Select
        value={status}
        onChange={onStatusChange}
        options={statusOptions}
      />
    </div>
  )
}
