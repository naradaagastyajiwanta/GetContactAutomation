import { SearchInput } from '../ui/SearchInput'
import { Select } from '../ui/Select'
import { useProvinces } from '../../hooks/useUniversities'
import { useUniversityGroups } from '../../hooks/useUniversityGroups'

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

const sortOptions = [
  { value: '', label: 'Terbaru Diupdate' },
  { value: 'student_count_desc', label: 'Mahasiswa Terbanyak' },
  { value: 'student_count_asc', label: 'Mahasiswa Tersedikit' },
  { value: 'name_asc', label: 'Nama A-Z' },
  { value: 'name_desc', label: 'Nama Z-A' },
  { value: 'province_asc', label: 'Provinsi A-Z' },
  { value: 'province_desc', label: 'Provinsi Z-A' },
  { value: 'created_at_desc', label: 'Terbaru Ditambahkan' },
  { value: 'created_at_asc', label: 'Terlama Ditambahkan' },
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
  sort: string
  onSortChange: (value: string) => void
  groupId: string
  onGroupChange: (value: string) => void
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
  sort,
  onSortChange,
  groupId,
  onGroupChange,
}: UniversityFiltersProps) {
  const { data: provinces } = useProvinces()
  const { data: groupsData } = useUniversityGroups()

  const provinceOptions = [
    { value: '', label: 'All Provinces' },
    ...(provinces ?? []).map((p) => ({ value: p, label: p })),
  ]

  const groupOptions = [
    { value: '', label: 'All Groups' },
    ...(groupsData?.groups ?? []).map((g) => ({
      value: String(g.id),
      label: `${g.name} (${g.university_count})`,
    })),
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
        <Select
          value={sort}
          onChange={onSortChange}
          options={sortOptions}
          className="w-48"
        />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={groupId}
          onChange={onGroupChange}
          options={groupOptions}
          className="min-w-[200px]"
        />
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
