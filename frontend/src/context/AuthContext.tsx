import { createContext, useContext, useEffect, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getCurrentUser } from '../api/auth'
import { queryKeys } from '../lib/queryKeys'
import type { AuthUser } from '../lib/types'

interface AuthContextValue {
  user: AuthUser | null
  isAuthenticated: boolean
  isLoading: boolean
  hasPermission: (permission?: string) => boolean
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  hasPermission: () => false,
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const meQuery = useQuery({
    queryKey: queryKeys.auth.me,
    queryFn: getCurrentUser,
    retry: false,
    staleTime: 5 * 60 * 1000,
  })

  useEffect(() => {
    function handleUnauthorized() {
      queryClient.setQueryData(queryKeys.auth.me, null)
      queryClient.invalidateQueries({ queryKey: queryKeys.auth.me })
    }

    window.addEventListener('app:unauthorized', handleUnauthorized)
    return () => window.removeEventListener('app:unauthorized', handleUnauthorized)
  }, [queryClient])

  const user = meQuery.data?.user ?? null
  const isAuthenticated = !!user

  function hasPermission(permission?: string) {
    if (!permission) return isAuthenticated
    if (!user) return false
    return user.permissions.includes('*') || user.permissions.includes(permission)
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated,
        isLoading: meQuery.isLoading,
        hasPermission,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}