import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react'
import { cn } from '../../lib/utils'

interface PaginationProps {
  currentPage: number
  totalPages: number
  onPageChange: (page: number) => void
}

export function Pagination({ currentPage, totalPages, onPageChange }: PaginationProps) {
  if (totalPages <= 1) return null

  const pages: (number | '...')[] = []
  for (let i = 1; i <= totalPages; i++) {
    if (i === 1 || i === totalPages || (i >= currentPage - 1 && i <= currentPage + 1)) {
      pages.push(i)
    } else if (pages[pages.length - 1] !== '...') {
      pages.push('...')
    }
  }

  const btnBase =
    'inline-flex items-center justify-center h-8 w-8 rounded text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed'

  return (
    <nav className="flex items-center gap-1">
      <button
        className={cn(btnBase, 'text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800')}
        onClick={() => onPageChange(1)}
        disabled={currentPage === 1}
      >
        <ChevronsLeft className="h-4 w-4" />
      </button>
      <button
        className={cn(btnBase, 'text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800')}
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage === 1}
      >
        <ChevronLeft className="h-4 w-4" />
      </button>

      {pages.map((page, idx) =>
        page === '...' ? (
          <span key={`ellipsis-${idx}`} className="px-1 text-gray-400">
            ...
          </span>
        ) : (
          <button
            key={page}
            className={cn(
              btnBase,
              page === currentPage
                ? 'bg-indigo-600 text-white dark:bg-indigo-500'
                : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800',
            )}
            onClick={() => onPageChange(page)}
          >
            {page}
          </button>
        ),
      )}

      <button
        className={cn(btnBase, 'text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800')}
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage === totalPages}
      >
        <ChevronRight className="h-4 w-4" />
      </button>
      <button
        className={cn(btnBase, 'text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800')}
        onClick={() => onPageChange(totalPages)}
        disabled={currentPage === totalPages}
      >
        <ChevronsRight className="h-4 w-4" />
      </button>
    </nav>
  )
}
