import { useState } from 'react'
import { Check, FileText, RefreshCw, X } from 'lucide-react'
import { Card } from '../ui/Card'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import {
  useApproveAudiensi,
  useRejectAudiensi,
  useUpdateRectorName,
  useUpdateInitialMessage,
  useRegeneratePdf,
} from '../../hooks/useAudiensi'
import type { AudiensiConversation } from '../../lib/types'

interface AudiensiApprovalCardProps {
  conversation: AudiensiConversation
}

export function AudiensiApprovalCard({ conversation }: AudiensiApprovalCardProps) {
  const [rectorName, setRectorName] = useState(conversation.rector_name ?? '')
  const [initialMessage, setInitialMessage] = useState(conversation.initial_message_draft ?? '')
  const [rectorDirty, setRectorDirty] = useState(false)
  const [messageDirty, setMessageDirty] = useState(false)

  const approveMutation = useApproveAudiensi()
  const rejectMutation = useRejectAudiensi()
  const updateRectorMutation = useUpdateRectorName()
  const updateMessageMutation = useUpdateInitialMessage()
  const regeneratePdfMutation = useRegeneratePdf()

  const handleSaveRector = () => {
    updateRectorMutation.mutate(
      { id: conversation.id, rectorName },
      { onSuccess: () => setRectorDirty(false) },
    )
  }

  const handleSaveMessage = () => {
    updateMessageMutation.mutate(
      { id: conversation.id, message: initialMessage },
      { onSuccess: () => setMessageDirty(false) },
    )
  }

  return (
    <Card>
      <div className="space-y-4">
        {/* Header */}
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100">
              {conversation.university_name ?? `University #${conversation.university_id}`}
            </h3>
            <div className="mt-1 flex items-center gap-3">
              {conversation.province && (
                <span className="text-sm text-gray-500 dark:text-gray-400">
                  {conversation.province}
                </span>
              )}
              <span className="font-mono text-sm text-gray-500 dark:text-gray-400">
                {conversation.contact_phone}
              </span>
            </div>
          </div>
          {conversation.contact_role && (
            <Badge className="bg-indigo-100 text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-300">
              {conversation.contact_role}
            </Badge>
          )}
        </div>

        {/* Rector Name */}
        <div>
          <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
            Rector Name
          </label>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={rectorName}
              onChange={(e) => {
                setRectorName(e.target.value)
                setRectorDirty(true)
              }}
              placeholder="Enter rector name..."
              className="flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm transition-colors focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 dark:focus:border-indigo-400 dark:focus:ring-indigo-400"
            />
            {rectorDirty && (
              <Button
                variant="secondary"
                size="sm"
                loading={updateRectorMutation.isPending}
                onClick={handleSaveRector}
              >
                Save
              </Button>
            )}
          </div>
        </div>

        {/* Initial Message Draft */}
        <div>
          <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
            Initial Message Draft
          </label>
          <textarea
            value={initialMessage}
            onChange={(e) => {
              setInitialMessage(e.target.value)
              setMessageDirty(true)
            }}
            rows={5}
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm transition-colors focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 dark:focus:border-indigo-400 dark:focus:ring-indigo-400"
          />
          {messageDirty && (
            <div className="mt-2 flex justify-end">
              <Button
                variant="secondary"
                size="sm"
                loading={updateMessageMutation.isPending}
                onClick={handleSaveMessage}
              >
                Save Message
              </Button>
            </div>
          )}
        </div>

        {/* PDF Status */}
        <div className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-3 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-gray-500 dark:text-gray-400" />
            {conversation.pdf_path ? (
              <Badge className="bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300">
                PDF Ready
              </Badge>
            ) : (
              <Badge className="bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300">
                PDF Not Generated
              </Badge>
            )}
          </div>
          <Button
            variant="secondary"
            size="sm"
            loading={regeneratePdfMutation.isPending}
            onClick={() => regeneratePdfMutation.mutate(conversation.id)}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            {conversation.pdf_path ? 'Regenerate' : 'Generate'}
          </Button>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-3 border-t border-gray-200 pt-4 dark:border-gray-700">
          <Button
            variant="primary"
            loading={approveMutation.isPending}
            onClick={() => approveMutation.mutate(conversation.id)}
            className="bg-green-600 hover:bg-green-700 focus:ring-green-500 dark:bg-green-600 dark:hover:bg-green-700"
          >
            <Check className="h-4 w-4" />
            Approve & Send
          </Button>
          <Button
            variant="danger"
            loading={rejectMutation.isPending}
            onClick={() => rejectMutation.mutate(conversation.id)}
          >
            <X className="h-4 w-4" />
            Reject
          </Button>
        </div>
      </div>
    </Card>
  )
}
