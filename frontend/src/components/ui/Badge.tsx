import type { ReactNode } from 'react'
import { cn } from '../../lib/utils'

interface BadgeProps {
  children: ReactNode
  className?: string
  variant?: string
}

export function Badge({ children, className, variant }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
        !variant && 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200',
        variant,
        className,
      )}
    >
      {children}
    </span>
  )
}
