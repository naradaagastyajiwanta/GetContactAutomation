import { cn } from '../../lib/utils'

interface SelectOption {
  value: string
  label: string
}

interface SelectProps {
  value: string
  onChange: (value: string) => void
  options: SelectOption[]
  placeholder?: string
  className?: string
}

export function Select({ value, onChange, options, placeholder, className }: SelectProps) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        'rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm transition-colors',
        'focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500',
        'dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 dark:focus:border-indigo-400 dark:focus:ring-indigo-400',
        className,
      )}
    >
      {placeholder && (
        <option value="" disabled>
          {placeholder}
        </option>
      )}
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  )
}
