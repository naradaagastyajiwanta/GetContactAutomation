import { useEffect, useState } from 'react'
import { Search } from 'lucide-react'
import { cn } from '../../lib/utils'

interface SearchInputProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
}

export function SearchInput({ value, onChange, placeholder = 'Search...', className }: SearchInputProps) {
  const [internal, setInternal] = useState(value)

  useEffect(() => {
    setInternal(value)
  }, [value])

  useEffect(() => {
    const timer = setTimeout(() => {
      if (internal !== value) {
        onChange(internal)
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [internal, onChange, value])

  return (
    <div className={cn('relative', className)}>
      <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
      <input
        type="text"
        value={internal}
        onChange={(e) => setInternal(e.target.value)}
        placeholder={placeholder}
        className={cn(
          'w-full rounded-lg border border-gray-300 bg-white py-2 pl-10 pr-4 text-sm placeholder-gray-400 transition-colors',
          'focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500',
          'dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500 dark:focus:border-indigo-400 dark:focus:ring-indigo-400',
        )}
      />
    </div>
  )
}
