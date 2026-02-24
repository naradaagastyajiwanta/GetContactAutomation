import { SearchInput } from '../ui/SearchInput'
import { Select } from '../ui/Select'
import { useProvinces } from '../../hooks/useUniversities'

const statusOptions = [
  { value: '', label: 'All Statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'ig_found', label: 'IG Found' },
  { value: 'ig_scraped', label: 'Scraped' },
  { value: 'contacted', label: 'Contacted' },
  { value: 'got_number', label: 'Got Number' },
  { value: 'failed', label: 'Failed' },
]

const igOptions = [
  { value: '', label: 'All IG Status' },
  { value: 'yes', label: 'Has IG Handle' },
  { value: 'no', label: 'No IG Handle' },
]

const enabledOptions = [
  { value: '', label: 'All (Enabled & Disabled)' },
  { value: 'yes', label: 'Enabled Only' },
  { value: 'no', label: 'Disabled Only' },
]

interface UniversityFiltersProps {
  search: string
  onSearchChange: (value: string) => void
  status: string
  onStatusChange: (value: string) => void
  province: string
  onProvinceChange: (value: string) => void
  hasIg: string
  onHasIgChange: (value: string) => void
  enabled: string
  onEnabledChange: (value: string) => void
}

export function UniversityFilters({
  search,
  onSearchChange,
  status,
  onStatusChange,
  province,
  onProvinceChange,
  hasIg,
  onHasIgChange,
  enabled,
  onEnabledChange,
}: UniversityFiltersProps) {
  const { data: provinces } = useProvinces()

  const provinceOptions = [
    { value: '', label: 'All Provinces' },
    ...(provinces ?? []).map((p) => ({ value: p, label: p })),
  ]

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-3 sm:flex-row">
        <SearchInput
          value={search}
          onChange={onSearchChange}
          placeholder="Search name, province, or IG handle..."
          className="flex-1"
        />
        <Select
          value={status}
          onChange={onStatusChange}
          options={statusOptions}
        />
      </div>
      <div className="flex flex-col gap-3 sm:flex-row">
        <Select
          value={province}
          onChange={onProvinceChange}
          options={provinceOptions}
        />
        <Select
          value={hasIg}
          onChange={onHasIgChange}
          options={igOptions}
        />
        <Select
          value={enabled}
          onChange={onEnabledChange}
          options={enabledOptions}
        />
      </div>
    </div>
  )
}
