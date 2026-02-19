import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '../../lib/utils'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  className?: string
  padding?: boolean
}

export function Card({ children, className, padding = true, ...rest }: CardProps) {
  return (
    <div
      className={cn(
        'rounded-lg border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800',
        padding && 'p-6',
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  )
}

export function CardHeader({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('mb-4', className)}>{children}</div>
}

export function CardTitle({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <h3 className={cn('text-lg font-semibold text-gray-900 dark:text-gray-100', className)}>
      {children}
    </h3>
  )
}

export function CardContent({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn(className)}>{children}</div>
}
