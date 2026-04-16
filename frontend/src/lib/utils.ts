import { clsx, type ClassValue } from 'clsx'
import { format, formatDistanceToNow } from 'date-fns'

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs)
}

export function formatDate(date: string | null): string {
  if (!date) return '-'
  return format(new Date(date), 'dd MMM yyyy HH:mm')
}

export function formatRelative(date: string | null): string {
  if (!date) return '-'
  return formatDistanceToNow(new Date(date), { addSuffix: true })
}

export function truncate(str: string, length: number): string {
  if (str.length <= length) return str
  return str.slice(0, length) + '...'
}

export function formatNumber(num: number | undefined | null): string {
  return new Intl.NumberFormat('id-ID').format(num ?? 0)
}
