import { useState } from 'react'
import { ExternalLink, Image, X, Instagram } from 'lucide-react'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../ui/Table'
import { Badge } from '../ui/Badge'
import { EmptyState } from '../ui/EmptyState'
import { truncate, formatDate } from '../../lib/utils'
import type { IgPost } from '../../lib/types'

interface PostsPanelProps {
  posts: IgPost[]
}

// Color coding for different IG source types
const SOURCE_TYPE_COLORS: Record<string, { bg: string; text: string; label: string }> = {
  main: { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-700 dark:text-blue-300', label: 'Official' },
  bem: { bg: 'bg-purple-100 dark:bg-purple-900/30', text: 'text-purple-700 dark:text-purple-300', label: 'BEM' },
  humas: { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-700 dark:text-green-300', label: 'Humas' },
  pmb: { bg: 'bg-orange-100 dark:bg-orange-900/30', text: 'text-orange-700 dark:text-orange-300', label: 'PMB' },
  kemahasiswaan: { bg: 'bg-teal-100 dark:bg-teal-900/30', text: 'text-teal-700 dark:text-teal-300', label: 'Kemahasiswaan' },
  alumni: { bg: 'bg-yellow-100 dark:bg-yellow-900/30', text: 'text-yellow-700 dark:text-yellow-300', label: 'Alumni' },
}

function getSourceBadge(type: string | null, handle: string | null) {
  if (!type) return null

  const config = SOURCE_TYPE_COLORS[type] || SOURCE_TYPE_COLORS.main
  return (
    <div className="inline-flex items-center gap-1.5" title={`From @${handle || 'unknown'}`}>
      <Badge className={config.bg + ' ' + config.text}>
        <Instagram className="h-3 w-3 mr-1" />
        {config.label}
      </Badge>
      {handle && (
        <span className="text-xs text-gray-500 dark:text-gray-400">@{handle}</span>
      )}
    </div>
  )
}

export function PostsPanel({ posts }: PostsPanelProps) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)

  if (posts.length === 0) {
    return (
      <EmptyState
        icon={Image}
        title="No posts found"
        description="No Instagram posts have been scraped for this university yet."
      />
    )
  }

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Image</TableHead>
            <TableHead>Source</TableHead>
            <TableHead>Post</TableHead>
            <TableHead>Caption</TableHead>
            <TableHead>Phones Found</TableHead>
            <TableHead>Extracted</TableHead>
            <TableHead>Date</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {posts.map((post) => (
            <TableRow key={post.id}>
              <TableCell>
                {post.image_url ? (
                  <img
                    src={post.image_url}
                    alt="Post"
                    className="h-12 w-12 rounded object-cover cursor-pointer hover:opacity-80 transition-opacity"
                    onClick={() => setPreviewUrl(post.image_url)}
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = 'none'
                    }}
                  />
                ) : (
                  <div className="h-12 w-12 rounded bg-gray-100 dark:bg-gray-700 flex items-center justify-center">
                    <Image className="h-5 w-5 text-gray-400" />
                  </div>
                )}
              </TableCell>
              <TableCell>
                {getSourceBadge(post.source_ig_type, post.source_ig_handle)}
              </TableCell>
              <TableCell>
                <a
                  href={post.post_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
                >
                  View
                  <ExternalLink className="h-3 w-3" />
                </a>
              </TableCell>
              <TableCell>
                {post.caption ? truncate(post.caption, 80) : '-'}
              </TableCell>
              <TableCell>{post.phones_found}</TableCell>
              <TableCell>
                {post.phone_extracted ? (
                  <Badge className="bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300">
                    Yes
                  </Badge>
                ) : (
                  <Badge className="bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300">
                    No
                  </Badge>
                )}
              </TableCell>
              <TableCell>{formatDate(post.post_timestamp)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {/* Image preview modal */}
      {previewUrl && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
          onClick={() => setPreviewUrl(null)}
        >
          <div className="relative max-h-[90vh] max-w-[90vw]">
            <button
              onClick={() => setPreviewUrl(null)}
              className="absolute -top-3 -right-3 rounded-full bg-white dark:bg-gray-800 p-1 shadow-lg hover:bg-gray-100 dark:hover:bg-gray-700"
            >
              <X className="h-5 w-5" />
            </button>
            <img
              src={previewUrl}
              alt="Post preview"
              className="max-h-[85vh] max-w-[85vw] rounded-lg object-contain"
            />
          </div>
        </div>
      )}
    </>
  )
}
