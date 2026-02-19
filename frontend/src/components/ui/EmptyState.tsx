import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '../../lib/utils'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description: string
  action?: ReactNode
  className?: string
}

export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center py-12 text-center', className)}>
      <Icon className="mb-4 h-12 w-12 text-gray-400 dark:text-gray-500" />
      <h3 className="mb-1 text-lg font-medium text-gray-900 dark:text-gray-100">{title}</h3>
      <p className="mb-4 max-w-sm text-sm text-gray-500 dark:text-gray-400">{description}</p>
      {action}
    </div>
  )
}
