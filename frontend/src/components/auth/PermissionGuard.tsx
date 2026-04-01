import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { Spinner } from '../ui/Spinner'

interface PermissionGuardProps {
  permission: string
  children: ReactNode
}

export function PermissionGuard({ permission, children }: PermissionGuardProps) {
  const { isLoading, hasPermission } = useAuth()

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }

  if (!hasPermission(permission)) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}