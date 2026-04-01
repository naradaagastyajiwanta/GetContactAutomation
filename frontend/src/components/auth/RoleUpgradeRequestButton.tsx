import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { ArrowUpCircle, Clock3, Send } from 'lucide-react'
import { createAuthRoleRequest, getMyAuthRoleRequests } from '../../api/auth'
import { useAuth } from '../../context/AuthContext'
import { queryKeys } from '../../lib/queryKeys'
import type { AuthRoleKey, AuthRoleUpgradeRequest, AuthRoleUpgradeRequestStatus } from '../../lib/types'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { Spinner } from '../ui/Spinner'

function normalizeErrorMessage(error: unknown): string {
  if (typeof error === 'object' && error && 'response' in error) {
    const response = (error as { response?: { data?: { detail?: string } } }).response
    if (response?.data?.detail) return response.data.detail
  }
  if (error instanceof Error) return error.message
  return 'Unexpected error'
}

function statusBadgeVariant(status: AuthRoleUpgradeRequestStatus): string {
  if (status === 'approved') {
    return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200'
  }
  if (status === 'rejected') {
    return 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-200'
  }
  return 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-200'
}

function formatRoleLabel(roleKey: AuthRoleKey): string {
  return roleKey.charAt(0).toUpperCase() + roleKey.slice(1)
}

export function RoleUpgradeRequestButton() {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const [isOpen, setIsOpen] = useState(false)
  const [roleKey, setRoleKey] = useState<AuthRoleKey>('operator')
  const [requestNote, setRequestNote] = useState('')

  const isViewerOnly = useMemo(() => {
    if (!user || user.roles.length === 0) return false
    return user.roles.every((currentRole) => currentRole === 'viewer')
  }, [user])

  const myRequestsQuery = useQuery({
    queryKey: queryKeys.auth.myRoleRequests,
    queryFn: () => getMyAuthRoleRequests(10),
    enabled: isViewerOnly,
  })

  const requests = myRequestsQuery.data?.requests ?? []
  const availableRoles = myRequestsQuery.data?.available_roles ?? []
  const pendingRequest = requests.find((entry) => entry.status === 'pending')

  const createMutation = useMutation({
    mutationFn: createAuthRoleRequest,
    onSuccess: async () => {
      toast.success('Role upgrade request sent to admin queue')
      setRequestNote('')
      setIsOpen(false)
      await queryClient.invalidateQueries({ queryKey: queryKeys.auth.myRoleRequests })
      await queryClient.invalidateQueries({ queryKey: queryKeys.auth.auditLogs })
    },
    onError: (error) => {
      toast.error(normalizeErrorMessage(error))
    },
  })

  if (!isViewerOnly) {
    return null
  }

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    createMutation.mutate({
      role_key: roleKey,
      request_note: requestNote.trim() || undefined,
    })
  }

  const handleOpen = () => {
    if (availableRoles.length > 0) {
      setRoleKey(availableRoles[0])
    }
    setIsOpen(true)
  }

  return (
    <>
      <Button type="button" variant={pendingRequest ? 'secondary' : 'outline'} size="sm" onClick={handleOpen}>
        {pendingRequest ? <Clock3 className="h-4 w-4" /> : <ArrowUpCircle className="h-4 w-4" />}
        {pendingRequest ? 'Upgrade Pending' : 'Request Upgrade'}
      </Button>

      <Modal isOpen={isOpen} onClose={() => setIsOpen(false)} title="Request Role Upgrade" size="md">
        {myRequestsQuery.isLoading ? (
          <div className="flex items-center justify-center py-10">
            <Spinner size="lg" />
          </div>
        ) : (
          <div className="space-y-4">
            <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-3 text-sm text-indigo-900 dark:border-indigo-900/50 dark:bg-indigo-950/30 dark:text-indigo-200">
              Request ini akan masuk ke queue admin. Admin mana pun yang aktif bisa langsung approve atau reject dari Settings &gt; Access.
            </div>

            {pendingRequest ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-900/50 dark:bg-amber-950/30">
                <p className="text-sm font-medium text-amber-900 dark:text-amber-200">You already have a pending request</p>
                <p className="mt-1 text-sm text-amber-800 dark:text-amber-300">
                  Requested role: {formatRoleLabel(pendingRequest.requested_role_key)}
                </p>
                {pendingRequest.request_note && (
                  <p className="mt-2 text-sm text-amber-800 dark:text-amber-300">Note: {pendingRequest.request_note}</p>
                )}
              </div>
            ) : availableRoles.length === 0 ? (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm text-gray-600 dark:border-gray-700 dark:bg-gray-900/40 dark:text-gray-300">
                No higher role is available for your account right now.
              </div>
            ) : (
              <form className="space-y-4" onSubmit={handleSubmit}>
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Requested role</label>
                  <select
                    value={roleKey}
                    onChange={(event) => setRoleKey(event.target.value as AuthRoleKey)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
                  >
                    {availableRoles.map((availableRole) => (
                      <option key={availableRole} value={availableRole}>
                        {formatRoleLabel(availableRole)}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Reason for request</label>
                  <textarea
                    value={requestNote}
                    onChange={(event) => setRequestNote(event.target.value)}
                    rows={4}
                    placeholder="Jelaskan kenapa Anda butuh akses yang lebih tinggi."
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
                  />
                </div>

                <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm text-gray-600 dark:border-gray-700 dark:bg-gray-900/40 dark:text-gray-300">
                  Setelah disetujui admin, refresh halaman untuk memuat akses baru ke UI.
                </div>

                <div className="flex justify-end gap-2">
                  <Button type="button" variant="ghost" onClick={() => setIsOpen(false)}>
                    Close
                  </Button>
                  <Button type="submit" loading={createMutation.isPending}>
                    <Send className="h-4 w-4" />
                    Send Request
                  </Button>
                </div>
              </form>
            )}

            {requests.length > 0 && (
              <div className="space-y-2 border-t border-gray-200 pt-4 dark:border-gray-700">
                <p className="text-sm font-medium text-gray-900 dark:text-gray-100">Recent requests</p>
                <div className="space-y-2">
                  {requests.slice(0, 5).map((entry: AuthRoleUpgradeRequest) => (
                    <div key={entry.id} className="rounded-lg border border-gray-200 p-3 dark:border-gray-700">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                            {formatRoleLabel(entry.current_role_key)} to {formatRoleLabel(entry.requested_role_key)}
                          </p>
                          <p className="text-xs text-gray-500 dark:text-gray-400">{new Date(entry.created_at).toLocaleString()}</p>
                        </div>
                        <Badge variant={statusBadgeVariant(entry.status)}>{entry.status}</Badge>
                      </div>
                      {entry.request_note && (
                        <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">{entry.request_note}</p>
                      )}
                      {entry.reviewed_by_email && (
                        <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                          Reviewed by {entry.reviewed_by_email}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>
    </>
  )
}