import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Brain, Phone } from 'lucide-react'
import { useConversation } from '../hooks/useConversations'
import { ChatBubble } from '../components/conversations/ChatBubble'
import { StateTimeline } from '../components/conversations/StateTimeline'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Spinner } from '../components/ui/Spinner'
import { CONVERSATION_STATE_COLORS } from '../lib/constants'
import { formatDate } from '../lib/utils'

export default function ConversationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: conversation, isLoading } = useConversation(Number(id) || 0)

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner size="lg" />
      </div>
    )
  }

  if (!conversation) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate('/conversations')}>
          <ArrowLeft className="h-4 w-4" />
          Back to Conversations
        </Button>
        <p className="text-center text-gray-500 dark:text-gray-400">Conversation not found.</p>
      </div>
    )
  }

  const stateColors = CONVERSATION_STATE_COLORS[conversation.state] ?? {
    bg: 'bg-gray-100 dark:bg-gray-700',
    text: 'text-gray-700 dark:text-gray-300',
  }

  return (
    <div className="space-y-6">
      <Button variant="ghost" onClick={() => navigate('/conversations')}>
        <ArrowLeft className="h-4 w-4" />
        Back to Conversations
      </Button>

      <Card>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
              {conversation.university_name ?? `University #${conversation.university_id}`}
            </h1>
            <p className="mt-1 font-mono text-sm text-gray-500 dark:text-gray-400">
              {conversation.contact_phone}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Badge className={`${stateColors.bg} ${stateColors.text}`}>
              {conversation.state.replace(/_/g, ' ')}
            </Badge>
            <span className="text-sm text-gray-500 dark:text-gray-400">
              {conversation.attempt_count} attempt{conversation.attempt_count !== 1 ? 's' : ''}
            </span>
          </div>
        </div>

        {conversation.extracted_number && (
          <div className="mt-4 flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-3 dark:border-green-800 dark:bg-green-900/30">
            <Phone className="h-5 w-5 text-green-600 dark:text-green-400" />
            <div>
              <p className="text-xs font-medium text-green-700 dark:text-green-300">
                Extracted Number
              </p>
              <p className="font-mono text-lg font-bold text-green-800 dark:text-green-200">
                {conversation.extracted_number}
              </p>
            </div>
          </div>
        )}

        <div className="mt-6">
          <StateTimeline currentState={conversation.state} />
        </div>
      </Card>

      <Card>
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
          Chat History
        </h2>
        {conversation.message_history.length === 0 ? (
          <p className="text-center text-sm text-gray-500 dark:text-gray-400">
            No messages yet.
          </p>
        ) : (
          <div className="space-y-3">
            {conversation.message_history.map((msg, idx) => (
              <ChatBubble key={idx} message={msg} />
            ))}
          </div>
        )}
      </Card>

      {conversation.agent_reasoning && (
        <Card>
          <div className="flex items-center gap-2 mb-3">
            <Brain className="h-5 w-5 text-indigo-500 dark:text-indigo-400" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Agent Reasoning
            </h2>
          </div>
          <p className="text-sm text-gray-600 dark:text-gray-400 whitespace-pre-wrap">
            {conversation.agent_reasoning}
          </p>
        </Card>
      )}

      <div className="text-sm text-gray-500 dark:text-gray-400">
        Created {formatDate(conversation.created_at)}
        {conversation.next_action_at && (
          <> &middot; Next action at {formatDate(conversation.next_action_at)}</>
        )}
      </div>
    </div>
  )
}
