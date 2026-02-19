import { useContext } from 'react'
import { useLocation } from 'react-router-dom'
import { Menu, Moon, Sun } from 'lucide-react'
import { ThemeContext } from '../../context/ThemeContext'
import { cn } from '../../lib/utils'

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

      <div className="flex items-center gap-3">
        <span
          className={cn(
            'h-2.5 w-2.5 rounded-full',
            'bg-green-500',
          )}
          title="System status: OK"
        />
        <button
          onClick={toggleTheme}
          className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
        >
          {theme === 'dark' ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </button>
      </div>
    </header>
  )
}
