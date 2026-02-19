import type { HTMLAttributes, ReactNode, TdHTMLAttributes, ThHTMLAttributes } from 'react'
import { cn } from '../../lib/utils'

export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className="overflow-x-auto">
      <table className={cn('min-w-full divide-y divide-gray-200 dark:divide-gray-700', className)}>
        {children}
      </table>
    </div>
  )
}

export function TableHeader({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <thead className={cn('bg-gray-50 dark:bg-gray-800/50', className)}>{children}</thead>
  )
}

export function TableBody({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <tbody className={cn('divide-y divide-gray-200 dark:divide-gray-700', className)}>
      {children}
    </tbody>
  )
}

export function TableRow({
  children,
  className,
  ...rest
}: HTMLAttributes<HTMLTableRowElement> & { children: ReactNode }) {
  return (
    <tr className={cn('hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors', className)} {...rest}>
      {children}
    </tr>
  )
}

export function TableHead({
  children,
  className,
  ...rest
}: ThHTMLAttributes<HTMLTableCellElement> & { children?: ReactNode }) {
  return (
    <th
      className={cn(
        'px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400',
        className,
      )}
      {...rest}
    >
      {children}
    </th>
  )
}

export function TableCell({
  children,
  className,
  ...rest
}: TdHTMLAttributes<HTMLTableCellElement> & { children?: ReactNode }) {
  return (
    <td
      className={cn('px-4 py-3 text-sm text-gray-700 dark:text-gray-300', className)}
      {...rest}
    >
      {children}
    </td>
  )
}
