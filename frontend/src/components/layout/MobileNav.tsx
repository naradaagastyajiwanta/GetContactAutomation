import { Link, useLocation } from 'react-router-dom'
import { Bot, X } from 'lucide-react'
import { cn } from '../../lib/utils'
import { navItems } from './Sidebar'

interface MobileNavProps {
  isOpen: boolean
  onClose: () => void
}

export function MobileNav({ isOpen, onClose }: MobileNavProps) {
  const { pathname } = useLocation()

  function isActive(to: string) {
    if (to === '/') return pathname === '/'
    return pathname.startsWith(to)
  }

  return (
    <>
      {isOpen && (
        <div className="fixed inset-0 z-40 bg-black/50 lg:hidden" onClick={onClose} />
      )}

      <div
        className={cn(
          'fixed inset-y-0 left-0 z-50 w-64 transform bg-white transition-transform duration-200 ease-in-out dark:bg-gray-900 lg:hidden',
          isOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex h-16 items-center justify-between border-b border-gray-200 px-6 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <Bot className="h-6 w-6 text-indigo-600 dark:text-indigo-400" />
            <span className="text-lg font-bold text-gray-900 dark:text-gray-100">GetContact AI</span>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="space-y-1 px-3 py-4">
          {navItems.map((item) => {
            const Icon = item.icon
            const active = isActive(item.to)
            return (
              <Link
                key={item.to}
                to={item.to}
                onClick={onClose}
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
      </div>
    </>
  )
}
