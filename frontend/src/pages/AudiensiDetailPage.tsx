import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Brain, Calendar, Video } from 'lucide-react'
import { useAudiensiConversation, useSendZoomLink } from '../hooks/useAudiensi'
import { ChatBubble } from '../components/conversations/ChatBubble'
import { AudiensiStateTimeline } from '../components/audiensi/AudiensiStateTimeline'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Spinner } from '../components/ui/Spinner'
import { AUDIENSI_STATE_COLORS } from '../lib/constants'
import { formatDate } from '../lib/utils'

export default function AudiensiDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: conversation, isLoading } = useAudiensiConversation(Number(id) || 0)
  const sendZoomMutation = useSendZoomLink()

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
        <Button variant="ghost" onClick={() => navigate('/audiensi')}>
          <ArrowLeft className="h-4 w-4" />
          Back to Audiensi
        </Button>
        <p className="text-center text-gray-500 dark:text-gray-400">Audiensi conversation not found.</p>
      </div>
    )
  }

  const stateColors = AUDIENSI_STATE_COLORS[conversation.state] ?? {
    bg: 'bg-gray-100 dark:bg-gray-700',
    text: 'text-gray-700 dark:text-gray-300',
  }

  return (
    <div className="space-y-6">
      <Button variant="ghost" onClick={() => navigate('/audiensi')}>
        <ArrowLeft className="h-4 w-4" />
        Back to Audiensi
      </Button>

      {/* Info Card */}
      <Card>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
              {conversation.university_name ?? `University #${conversation.university_id}`}
            </h1>
            <p className="mt-1 font-mono text-sm text-gray-500 dark:text-gray-400">
              {conversation.contact_phone}
            </p>
            {conversation.province && (
              <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
                {conversation.province}
              </p>
            )}
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

        {/* Rector Name */}
        {conversation.rector_name && (
          <div className="mt-4 flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3 dark:border-indigo-800 dark:bg-indigo-900/30">
            <div>
              <p className="text-xs font-medium text-indigo-700 dark:text-indigo-300">
                Rector Name
              </p>
              <p className="text-sm font-semibold text-indigo-800 dark:text-indigo-200">
                {conversation.rector_name}
              </p>
            </div>
          </div>
        )}

        {/* Scheduled Datetime */}
        {conversation.state === 'SCHEDULED' && conversation.scheduled_datetime && (
          <div className="mt-4 flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-3 dark:border-green-800 dark:bg-green-900/30">
            <Calendar className="h-5 w-5 text-green-600 dark:text-green-400" />
            <div>
              <p className="text-xs font-medium text-green-700 dark:text-green-300">
                Scheduled Datetime
              </p>
              <p className="font-mono text-lg font-bold text-green-800 dark:text-green-200">
                {formatDate(conversation.scheduled_datetime)}
              </p>
            </div>
          </div>
        )}

        {/* Zoom Link */}
        {conversation.state === 'ZOOM_SENT' && conversation.zoom_link && (
          <div className="mt-4 flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-3 dark:border-green-800 dark:bg-green-900/30">
            <Video className="h-5 w-5 text-green-600 dark:text-green-400" />
            <div>
              <p className="text-xs font-medium text-green-700 dark:text-green-300">
                Zoom Link
              </p>
              <a
                href={conversation.zoom_link}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-medium text-green-700 underline hover:text-green-800 dark:text-green-300 dark:hover:text-green-200"
              >
                {conversation.zoom_link}
              </a>
            </div>
          </div>
        )}

        {/* State Timeline */}
        <div className="mt-6">
          <AudiensiStateTimeline currentState={conversation.state} />
        </div>
      </Card>

      {/* Chat History */}
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

      {/* Agent Reasoning */}
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

      {/* Send Zoom Link action */}
      {conversation.state === 'SCHEDULED' && (
        <Card>
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                Send Zoom Link
              </h3>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                Send the Zoom meeting link to the contact via WhatsApp.
              </p>
            </div>
            <Button
              variant="primary"
              loading={sendZoomMutation.isPending}
              onClick={() => sendZoomMutation.mutate(conversation.id)}
            >
              <Video className="h-4 w-4" />
              Send Zoom Link
            </Button>
          </div>
        </Card>
      )}

      {/* Footer info */}
      <div className="text-sm text-gray-500 dark:text-gray-400">
        Created {formatDate(conversation.created_at)}
        {conversation.last_message_at && (
          <> &middot; Last message {formatDate(conversation.last_message_at)}</>
        )}
        {conversation.approved_at && (
          <> &middot; Approved {formatDate(conversation.approved_at)}</>
        )}
      </div>
    </div>
  )
}
