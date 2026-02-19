import { ExternalLink, Image } from 'lucide-react'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../ui/Table'
import { Badge } from '../ui/Badge'
import { EmptyState } from '../ui/EmptyState'
import { truncate, formatDate } from '../../lib/utils'
import type { IgPost } from '../../lib/types'

interface PostsPanelProps {
  posts: IgPost[]
}

export function PostsPanel({ posts }: PostsPanelProps) {
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
    <Table>
      <TableHeader>
        <TableRow>
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
  )
}
