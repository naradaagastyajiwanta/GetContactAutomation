import { useQuery } from '@tanstack/react-query'
import { History, RefreshCw, ShieldCheck, ShieldX } from 'lucide-react'
import { getAuthAuditLogs } from '../../api/auth'
import { queryKeys } from '../../lib/queryKeys'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/Card'
import { Spinner } from '../ui/Spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/Table'

function actionLabel(action: string): string {
  return action
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function resultBadgeVariant(success: boolean): string {
  return success
    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200'
    : 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-200'
}

export function AuthAuditLogViewer() {
  const auditQuery = useQuery({
    queryKey: queryKeys.auth.auditLogs,
    queryFn: () => getAuthAuditLogs(50, 0),
  })

  const logs = auditQuery.data?.logs ?? []
  const total = auditQuery.data?.total ?? 0

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <History className="h-5 w-5 text-indigo-500" />
              <CardTitle>Auth Audit Trail</CardTitle>
            </div>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Recent login and access-management activity for dashboard security review.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-500 dark:text-gray-400">{total} event(s)</span>
            <Button type="button" variant="outline" size="sm" onClick={() => auditQuery.refetch()} loading={auditQuery.isFetching}>
              <RefreshCw className="h-4 w-4" />
              Refresh
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        {auditQuery.isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Spinner size="lg" />
          </div>
        ) : logs.length === 0 ? (
          <div className="rounded-lg border border-dashed border-gray-300 px-6 py-12 text-center dark:border-gray-700">
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">No auth audit events yet</p>
            <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">Events will appear here after login, grant, revoke, bootstrap, and logout actions.</p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Target</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Result</TableHead>
                <TableHead>Detail</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {logs.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell>
                    <div>
                      <p className="font-medium text-gray-900 dark:text-gray-100">{new Date(entry.created_at).toLocaleDateString()}</p>
                      <p className="text-xs text-gray-500 dark:text-gray-400">{new Date(entry.created_at).toLocaleTimeString()}</p>
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className="font-medium text-gray-900 dark:text-gray-100">{actionLabel(entry.action)}</span>
                  </TableCell>
                  <TableCell>
                    <span className="text-sm text-gray-600 dark:text-gray-300">{entry.actor_email || 'system'}</span>
                  </TableCell>
                  <TableCell>
                    <span className="text-sm text-gray-600 dark:text-gray-300">{entry.subject_email || '-'}</span>
                  </TableCell>
                  <TableCell>
                    {entry.role_key ? <Badge>{entry.role_key}</Badge> : <span className="text-sm text-gray-400">-</span>}
                  </TableCell>
                  <TableCell>
                    <Badge variant={resultBadgeVariant(entry.success)}>
                      {entry.success ? <ShieldCheck className="mr-1 h-3.5 w-3.5" /> : <ShieldX className="mr-1 h-3.5 w-3.5" />}
                      {entry.success ? 'Success' : 'Failed'}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="max-w-md text-sm text-gray-600 dark:text-gray-300">{entry.detail || '-'}</div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}