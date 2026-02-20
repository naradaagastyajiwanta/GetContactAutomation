import { Link, useLocation } from 'react-router-dom'
import {
  Bot,
  LayoutDashboard,
  GraduationCap,
  GitBranch,
  MessageSquare,
  Lightbulb,
  Smartphone,
  Settings,
} from 'lucide-react'
import { cn } from '../../lib/utils'

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/universities', label: 'Universities', icon: GraduationCap },
  { to: '/pipeline', label: 'Pipeline', icon: GitBranch },
  { to: '/conversations', label: 'Conversations', icon: MessageSquare },
  { to: '/learning', label: 'Learning', icon: Lightbulb },
  { to: '/whatsapp', label: 'WhatsApp', icon: Smartphone },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function Sidebar() {
  const { pathname } = useLocation()

  function isActive(to: string) {
    if (to === '/') return pathname === '/'
    return pathname.startsWith(to)
  }

  return (
    <aside className="flex h-full w-64 flex-col border-r border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
      <div className="flex h-16 items-center gap-2 border-b border-gray-200 px-6 dark:border-gray-700">
        <Bot className="h-6 w-6 text-indigo-600 dark:text-indigo-400" />
        <span className="text-lg font-bold text-gray-900 dark:text-gray-100">GetContact AI</span>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map((item) => {
          const Icon = item.icon
          const active = isActive(item.to)
          return (
            <Link
              key={item.to}
              to={item.to}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                active
                  ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300'
                  : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100',
              )}
            >
              <Icon className="h-5 w-5" />
              {item.label}
            </Link>
          )
        })}
      </nav>
    </aside>
  )
}

export { navItems }
