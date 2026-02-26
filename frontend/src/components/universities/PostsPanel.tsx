import { useState } from 'react'
import { ExternalLink, X, Instagram, Image } from 'lucide-react'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../ui/Table'
import { Badge } from '../ui/Badge'
import { EmptyState } from '../ui/EmptyState'
import { truncate, formatDate } from '../../lib/utils'
import { getFreshInstagramImageUrl } from '../../lib/instagram'
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
  const [loadingImages, setLoadingImages] = useState<Set<number>>(new Set())
  const [freshImageUrls, setFreshImageUrls] = useState<Map<number, string>>(new Map())

  // Fetch fresh image URL when clicked
  const handleImageClick = async (post: IgPost) => {
    // If we already have a fresh URL, use it
    if (freshImageUrls.has(post.id)) {
      setPreviewUrl(freshImageUrls.get(post.id)!)
      return
    }

    // Otherwise, fetch fresh URL from Instagram
    setLoadingImages(prev => new Set(prev).add(post.id))

    try {
      const freshUrl = await getFreshInstagramImageUrl(post.post_url)

      if (freshUrl) {
        // Cache the fresh URL
        setFreshImageUrls(prev => new Map(prev).set(post.id, freshUrl))
        setPreviewUrl(freshUrl)
      } else {
        // Fallback to opening Instagram directly
        window.open(post.post_url, '_blank')
      }
    } catch (error) {
      console.error('Failed to fetch fresh image URL:', error)
      // Fallback to opening Instagram directly
      window.open(post.post_url, '_blank')
    } finally {
      setLoadingImages(prev => {
        const newSet = new Set(prev)
        newSet.delete(post.id)
        return newSet
      })
    }
  }

  // Get display URL for thumbnail (prefer fresh URL, fallback to cached)
  const getDisplayUrl = (post: IgPost): string => {
    return freshImageUrls.get(post.id) || post.image_url || ''
  }

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
      {/* Info banner - always show when there are posts */}
      {posts.length > 0 && (
        <div className="mb-4 p-4 bg-gradient-to-r from-green-50 to-emerald-50 dark:from-green-900/30 dark:to-emerald-900/30 rounded-lg border border-green-200 dark:border-green-700">
          <div className="flex items-start gap-3">
            <Instagram className="h-6 w-6 text-green-600 dark:text-green-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <div className="font-medium text-green-900 dark:text-green-300 text-sm">
                Instagram Posts Loaded
              </div>
              <div className="text-green-800 dark:text-green-400 text-sm mt-1">
                Click on any image thumbnail to view the full-size version. Use <strong className="underline decoration-2">"View on IG"</strong> to see the post on Instagram with full caption and comments.
              </div>
            </div>
          </div>
        </div>
      )}

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
                  <div className="relative">
                    <img
                      src={getDisplayUrl(post)}
                      alt="Post thumbnail"
                      className="h-16 w-16 rounded-lg object-cover cursor-pointer hover:opacity-90 transition-opacity shadow-sm"
                      onClick={() => handleImageClick(post)}
                      loading="lazy"
                    />
                    {loadingImages.has(post.id) && (
                      <div className="absolute inset-0 bg-black/50 rounded-lg flex items-center justify-center">
                        <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="h-16 w-16 rounded-lg bg-gray-100 dark:bg-gray-700 flex items-center justify-center">
                    <Image className="h-6 w-6 text-gray-400" />
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
                  className="inline-flex items-center gap-1.5 text-sm font-medium text-white bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 px-3 py-1.5 rounded-md transition-all shadow-sm hover:shadow"
                >
                  <Instagram className="h-4 w-4" />
                  View on IG
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

      {/* Image preview modal - shows full image */}
      {previewUrl && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80"
          onClick={() => setPreviewUrl(null)}
        >
          <div className="relative max-h-[90vh] max-w-[90vw]" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => setPreviewUrl(null)}
              className="absolute -top-4 -right-4 z-10 rounded-full bg-white dark:bg-gray-700 p-2 shadow-lg hover:bg-gray-100 dark:hover:bg-gray-600"
            >
              <X className="h-6 w-6 text-gray-800 dark:text-gray-200" />
            </button>
            <img
              src={previewUrl}
              alt="Full size post image"
              className="max-h-[90vh] max-w-[90vw] rounded-lg shadow-2xl"
            />
          </div>
        </div>
      )}
    </>
  )
}
