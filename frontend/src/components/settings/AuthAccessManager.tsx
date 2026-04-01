import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { KeyRound, Shield, ShieldAlert, Trash2, UserPlus, Users } from 'lucide-react'
import { getAuthAccess, grantAuthRole, revokeAuthRole } from '../../api/auth'
import { useAuth } from '../../context/AuthContext'
import { queryKeys } from '../../lib/queryKeys'
import type { AuthAccessAssignment, AuthRoleKey } from '../../lib/types'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/Card'
import { Spinner } from '../ui/Spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/Table'

function roleBadgeVariant(roleKey: AuthRoleKey): string {
  if (roleKey === 'admin') {
    return 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-200'
  }
  if (roleKey === 'operator') {
    return 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-200'
  }
  return 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-200'
}

function normalizeErrorMessage(error: unknown): string {
  if (typeof error === 'object' && error && 'response' in error) {
    const response = (error as { response?: { data?: { detail?: string } } }).response
    if (response?.data?.detail) return response.data.detail
  }
  if (error instanceof Error) return error.message
  return 'Unexpected error'
}

function countAssignments(assignments: AuthAccessAssignment[], roleKey: AuthRoleKey): number {
  return assignments.filter((assignment) => assignment.role_key === roleKey).length
}

export function AuthAccessManager() {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const [email, setEmail] = useState('')
  const [roleKey, setRoleKey] = useState<AuthRoleKey>('viewer')

  const accessQuery = useQuery({
    queryKey: queryKeys.auth.access,
    queryFn: getAuthAccess,
  })

  const assignments = accessQuery.data?.assignments ?? []
  const roles = accessQuery.data?.roles ?? []
  const adminCount = useMemo(() => countAssignments(assignments, 'admin'), [assignments])

  const refreshAuthData = async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.auth.access })
    await queryClient.invalidateQueries({ queryKey: queryKeys.auth.me })
  }

  const grantMutation = useMutation({
    mutationFn: grantAuthRole,
    onSuccess: async () => {
      toast.success('Access granted')
      setEmail('')
      setRoleKey('viewer')
      await refreshAuthData()
    },
    onError: (error) => {
      toast.error(normalizeErrorMessage(error))
    },
  })

  const revokeMutation = useMutation({
    mutationFn: revokeAuthRole,
    onSuccess: async () => {
      toast.success('Access revoked')
      await refreshAuthData()
    },
    onError: (error) => {
      toast.error(normalizeErrorMessage(error))
    },
  })

  const handleGrant = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    grantMutation.mutate({ email: email.trim(), role_key: roleKey })
  }

  const canRevoke = (assignment: AuthAccessAssignment): boolean => {
    if (assignment.role_key === 'admin' && adminCount <= 1) {
      return false
    }
    return true
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
        <Card>
          <CardHeader>
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle>Grant Access</CardTitle>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                  Assign a local dashboard role to any active DMS user by email.
                </p>
              </div>
              <div className="rounded-lg bg-indigo-50 p-2 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-300">
                <UserPlus className="h-5 w-5" />
              </div>
            </div>
          </CardHeader>

          <CardContent>
            <form className="space-y-4" onSubmit={handleGrant}>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">DMS Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="name@company.com"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
                  required
                />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Role</label>
                <select
                  value={roleKey}
                  onChange={(event) => setRoleKey(event.target.value as AuthRoleKey)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
                >
                  {roles.map((role) => (
                    <option key={role.key} value={role.key}>
                      {role.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm text-gray-600 dark:border-gray-700 dark:bg-gray-900/50 dark:text-gray-300">
                <div className="flex items-start gap-2">
                  <KeyRound className="mt-0.5 h-4 w-4 shrink-0 text-gray-400" />
                  <p>
                    User must exist in DMS and still be active. Granting a role updates local dashboard access only.
                  </p>
                </div>
              </div>

              <Button type="submit" className="w-full justify-center" loading={grantMutation.isPending}>
                Grant Access
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle>Access Summary</CardTitle>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                  Current local access assignments and admin safety status.
                </p>
              </div>
              <div className="rounded-lg bg-emerald-50 p-2 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-300">
                <Users className="h-5 w-5" />
              </div>
            </div>
          </CardHeader>

          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-gray-200 p-4 dark:border-gray-700">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Admins</p>
                <p className="mt-2 text-2xl font-semibold text-gray-900 dark:text-gray-100">{adminCount}</p>
              </div>
              <div className="rounded-lg border border-gray-200 p-4 dark:border-gray-700">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Operators</p>
                <p className="mt-2 text-2xl font-semibold text-gray-900 dark:text-gray-100">{countAssignments(assignments, 'operator')}</p>
              </div>
              <div className="rounded-lg border border-gray-200 p-4 dark:border-gray-700">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Viewers</p>
                <p className="mt-2 text-2xl font-semibold text-gray-900 dark:text-gray-100">{countAssignments(assignments, 'viewer')}</p>
              </div>
            </div>

            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-900/50 dark:bg-amber-950/30">
              <div className="flex items-start gap-3">
                <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-amber-600 dark:text-amber-300" />
                <div>
                  <p className="text-sm font-medium text-amber-900 dark:text-amber-200">Admin safety guard enabled</p>
                  <p className="mt-1 text-sm text-amber-800 dark:text-amber-300">
                    The last active admin cannot be revoked from the dashboard. Add another admin first if you need to rotate ownership.
                  </p>
                </div>
              </div>
            </div>

            {user && (
              <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900/40">
                <div className="flex items-center gap-2 text-sm font-medium text-gray-900 dark:text-gray-100">
                  <Shield className="h-4 w-4 text-indigo-500" />
                  Signed in as {user.name}
                </div>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{user.email}</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Assigned Users</CardTitle>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Revoke specific local roles without touching the underlying DMS account.
          </p>
        </CardHeader>

        <CardContent>
          {accessQuery.isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Spinner size="lg" />
            </div>
          ) : assignments.length === 0 ? (
            <div className="rounded-lg border border-dashed border-gray-300 px-6 py-12 text-center dark:border-gray-700">
              <p className="text-sm font-medium text-gray-900 dark:text-gray-100">No access assignments yet</p>
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">Grant the first user above to start managing dashboard access.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Granted By</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {assignments.map((assignment) => {
                  const disabled = revokeMutation.isPending || !canRevoke(assignment)
                  const isSelf = assignment.user_email === user?.email

                  return (
                    <TableRow key={assignment.id}>
                      <TableCell>
                        <div>
                          <p className="font-medium text-gray-900 dark:text-gray-100">{assignment.user_name}</p>
                          <p className="text-xs text-gray-500 dark:text-gray-400">{assignment.user_email}</p>
                          {isSelf && <p className="mt-1 text-xs text-indigo-600 dark:text-indigo-300">Current session</p>}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={roleBadgeVariant(assignment.role_key)}>{assignment.role_key}</Badge>
                      </TableCell>
                      <TableCell>
                        <span className="text-sm text-gray-500 dark:text-gray-400">
                          {assignment.granted_by_email || 'system:auto-grant'}
                        </span>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={disabled}
                          onClick={() => revokeMutation.mutate({ dms_user_id: assignment.dms_user_id, role_key: assignment.role_key })}
                        >
                          <Trash2 className="h-4 w-4" />
                          Revoke
                        </Button>
                        {!canRevoke(assignment) && (
                          <p className="mt-1 text-xs text-amber-600 dark:text-amber-300">Last admin cannot be revoked</p>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}