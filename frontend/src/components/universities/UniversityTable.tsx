import { useNavigate } from 'react-router-dom'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../ui/Table'
import { Badge } from '../ui/Badge'
import { STATUS_COLORS } from '../../lib/constants'
import { formatDate } from '../../lib/utils'
import type { University } from '../../lib/types'

interface UniversityTableProps {
  universities: University[]
}

export function UniversityTable({ universities }: UniversityTableProps) {
  const navigate = useNavigate()

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Province</TableHead>
          <TableHead>IG Handle</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Created</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {universities.map((uni) => {
          const colors = STATUS_COLORS[uni.status] || STATUS_COLORS.pending
          return (
            <TableRow
              key={uni.id}
              className="cursor-pointer"
            >
              <TableCell>
                <button
                  className="text-left font-medium text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
                  onClick={() => navigate(`/universities/${uni.id}`)}
                >
                  {uni.name}
                </button>
              </TableCell>
              <TableCell>{uni.province || '-'}</TableCell>
              <TableCell>
                {uni.ig_handle ? (
                  <span className="text-gray-700 dark:text-gray-300">@{uni.ig_handle}</span>
                ) : (
                  '-'
                )}
              </TableCell>
              <TableCell>
                <Badge className={`${colors.bg} ${colors.text}`}>
                  {uni.status}
                </Badge>
              </TableCell>
              <TableCell>{formatDate(uni.created_at)}</TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
