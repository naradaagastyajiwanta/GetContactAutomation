import { Copy, CheckCircle2, ExternalLink } from 'lucide-react'
import toast from 'react-hot-toast'
import { formatDistanceToNow } from 'date-fns'
import { type PhoneNumber } from '../../api/phoneNumbers'
import { Button } from '../ui/Button'

interface PhoneNumberTableProps {
  data: PhoneNumber[]
  isLoading: boolean
}

export function PhoneNumberTable({ data, isLoading }: PhoneNumberTableProps) {
  const copyToClipboard = (phone: string) => {
    navigator.clipboard.writeText(phone)
    toast.success('Copied to clipboard!')
  }

  if (isLoading) {
    return (
      <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
        <table className="w-full">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900 dark:text-gray-100">
                Phone Number
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900 dark:text-gray-100">
                Contact
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900 dark:text-gray-100">
                University
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900 dark:text-gray-100">
                Added
              </th>
            </tr>
          </thead>
          <tbody>
            {[...Array(5)].map((_, i) => (
              <tr key={i} className="border-t border-gray-200 dark:border-gray-700">
                <td className="px-6 py-4">
                  <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-32 animate-pulse" />
                </td>
                <td className="px-6 py-4">
                  <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-24 animate-pulse" />
                </td>
                <td className="px-6 py-4">
                  <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-40 animate-pulse" />
                </td>
                <td className="px-6 py-4">
                  <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-28 animate-pulse" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-12 text-center dark:border-gray-700 dark:bg-gray-800">
        <CheckCircle2 className="mx-auto h-12 w-12 text-gray-400 dark:text-gray-600 mb-4" />
        <p className="text-gray-600 dark:text-gray-400">No phone numbers found</p>
        <p className="text-sm text-gray-500 dark:text-gray-500 mt-1">
          Start collecting contacts from Instagram to see them here
        </p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
      <table className="w-full">
        <thead className="bg-gray-50 dark:bg-gray-800">
          <tr>
            <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900 dark:text-gray-100">
              Phone Number
            </th>
            <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900 dark:text-gray-100">
              Contact Name
            </th>
            <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900 dark:text-gray-100">
              University
            </th>
            <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900 dark:text-gray-100">
              Province
            </th>
            <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900 dark:text-gray-100">
              Added
            </th>
            <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900 dark:text-gray-100">
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr
              key={row.id}
              className="border-t border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
            >
              <td className="px-6 py-4 text-sm font-mono text-gray-900 dark:text-gray-100">
                {row.phone_number}
              </td>
              <td className="px-6 py-4 text-sm text-gray-700 dark:text-gray-300">
                {row.contact_name || '—'}
              </td>
              <td className="px-6 py-4 text-sm text-gray-700 dark:text-gray-300">
                {row.university_name || '—'}
              </td>
              <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400">
                {row.province || '—'}
              </td>
              <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400">
                {formatDistanceToNow(new Date(row.created_at), { addSuffix: true })}
              </td>
              <td className="px-6 py-4 text-sm">
                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => copyToClipboard(row.phone_number)}
                    title="Copy phone number"
                    className="text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 p-1 h-auto"
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                  {row.source_post_url && (
                    <a
                      href={row.source_post_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100 p-1 h-auto"
                      title="View source post"
                    >
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
