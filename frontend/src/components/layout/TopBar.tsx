import { useContext } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { LogOut, Menu, Moon, Sun } from 'lucide-react'
import { ThemeContext } from '../../context/ThemeContext'
import { NotificationCenter } from '../notifications/NotificationCenter'
import { useAuth } from '../../context/AuthContext'
import { logout } from '../../api/auth'
import { queryKeys } from '../../lib/queryKeys'

const pageTitles: Record<string, string> = {
  '/': 'Dashboard',
  '/universities': 'Universities',
  '/pipeline': 'Pipeline',
  '/conversations': 'Conversations',
  '/settings': 'Settings',
}

function getPageTitle(pathname: string): string {
  if (pageTitles[pathname]) return pageTitles[pathname]
  if (pathname.startsWith('/universities/')) return 'University Detail'
  if (pathname.startsWith('/conversations/')) return 'Conversation Detail'
  return 'Dashboard'
}

interface TopBarProps {
  onMenuClick: () => void
}

export function TopBar({ onMenuClick }: TopBarProps) {
  const { pathname } = useLocation()
  const { theme, toggleTheme } = useContext(ThemeContext)
  const { user } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const logoutMutation = useMutation({
    mutationFn: logout,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.auth.me })
      navigate('/login', { replace: true })
    },
  })

  return (
    <header className="flex h-16 items-center justify-between border-b border-gray-200 bg-white px-4 dark:border-gray-700 dark:bg-gray-900 lg:px-6">
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuClick}
          className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800 lg:hidden"
        >
          <Menu className="h-5 w-5" />
        </button>
        <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          {getPageTitle(pathname)}
        </h1>
      </div>

      <div className="flex items-center gap-2">
        {user && (
          <div className="hidden items-center rounded-lg border border-gray-200 px-3 py-1.5 text-right dark:border-gray-700 md:flex">
            <div>
              <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{user.name}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{user.email}</p>
            </div>
          </div>
        )}
        <NotificationCenter />
        <button
          onClick={toggleTheme}
          className="flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
        >
          {theme === 'dark' ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </button>
        <button
          onClick={() => logoutMutation.mutate()}
          className="flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
          title="Logout"
        >
          <LogOut className="h-5 w-5" />
        </button>
      </div>
    </header>
  )
}
