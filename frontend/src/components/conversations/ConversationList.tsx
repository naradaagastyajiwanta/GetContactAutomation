import { useNavigate } from 'react-router-dom'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../ui/Table'
import { Badge } from '../ui/Badge'
import { CONVERSATION_STATE_COLORS } from '../../lib/constants'
import { formatRelative } from '../../lib/utils'
import type { Conversation } from '../../lib/types'

interface ConversationListProps {
  conversations: Conversation[]
}

export function ConversationList({ conversations }: ConversationListProps) {
  const navigate = useNavigate()

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>University</TableHead>
          <TableHead>Phone</TableHead>
          <TableHead>State</TableHead>
          <TableHead>Last Message</TableHead>
          <TableHead>Attempts</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {conversations.map((conv) => {
          const colors = CONVERSATION_STATE_COLORS[conv.state] ?? {
            bg: 'bg-gray-100 dark:bg-gray-700',
            text: 'text-gray-700 dark:text-gray-300',
          }
          return (
            <TableRow
              key={conv.id}
              className="cursor-pointer"
              onClick={() => navigate(`/conversations/${conv.id}`)}
            >
              <TableCell className="font-medium">
                {conv.university_name ?? `University #${conv.university_id}`}
              </TableCell>
              <TableCell className="font-mono text-xs">{conv.contact_phone}</TableCell>
              <TableCell>
                <Badge className={`${colors.bg} ${colors.text}`}>
                  {conv.state.replace(/_/g, ' ')}
                </Badge>
              </TableCell>
              <TableCell>{formatRelative(conv.last_message_at)}</TableCell>
              <TableCell>{conv.attempt_count}</TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
