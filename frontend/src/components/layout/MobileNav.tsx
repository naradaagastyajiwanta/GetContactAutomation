import { Link, useLocation } from 'react-router-dom'
import { Bot, X, Settings, type LucideIcon } from 'lucide-react'
import { cn } from '../../lib/utils'
import { NAV_SECTIONS } from './Sidebar'

interface MobileNavProps {
  isOpen: boolean
  onClose: () => void
}

function isActivePath(pathname: string, to: string): boolean {
  if (to === '/') return pathname === '/'
  return pathname.startsWith(to)
}

export function MobileNav({ isOpen, onClose }: MobileNavProps) {
  const { pathname } = useLocation()

  const activeSection = NAV_SECTIONS.find((section) =>
    section.items.some((item) => isActivePath(pathname, item.to)),
  )

  return (
    <>
      {isOpen && (
        <div className="fixed inset-0 z-40 bg-black/40 lg:hidden" onClick={onClose} />
      )}

      <div
        className={cn(
          'fixed inset-y-0 left-0 z-50 w-[220px] transform bg-white transition-transform duration-200 ease-out dark:bg-[#111827] lg:hidden',
          isOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        {/* Brand */}
        <div className="flex h-14 items-center justify-between border-b border-gray-100 px-5 dark:border-gray-800/80">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gray-900 dark:bg-indigo-600">
              <Bot className="h-4 w-4 text-white" />
            </div>
            <span className="text-sm font-semibold text-gray-900 dark:text-white">
              DMS Marketing
            </span>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 space-y-3 overflow-y-auto px-3 py-4 scrollbar-thin">
          {NAV_SECTIONS.map((section, idx) => {
            const Icon: LucideIcon = section.icon

            return (
              <div key={section.id}>
                {/* Section divider */}
                {idx > 0 && (
                  <div className="mb-3 mt-1 border-t border-gray-100 dark:border-gray-800/80" />
                )}

                <div className="mb-1 flex items-center gap-2 px-2 text-[11px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
                  <Icon className="h-3.5 w-3.5 opacity-50" />
                  {section.label}
                </div>

                <div className="space-y-0.5">
                  {section.items.map((item) => {
                    const active = isActivePath(pathname, item.to)
                    const ItemIcon: LucideIcon = item.icon

                    return (
                      <Link
                        key={item.to}
                        to={item.to}
                        onClick={onClose}
                        className={cn(
                          'group relative mb-0.5 flex items-center gap-2.5 rounded-lg px-2 py-2 text-[13px] font-medium transition-all duration-150',
                          active
                            ? 'bg-gray-900 text-white dark:bg-indigo-600 dark:text-white'
                            : 'text-gray-500 hover:bg-gray-50 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800/60 dark:hover:text-white',
                        )}
                      >
                        <ItemIcon className="h-4 w-4 shrink-0 opacity-70" />
                        {item.label}
                      </Link>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </nav>

        {/* Settings */}
        <div className="border-t border-gray-100 px-3 py-4 dark:border-gray-800/80">
          <Link
            to="/settings"
            onClick={onClose}
            className={cn(
              'flex items-center gap-2.5 rounded-lg px-2 py-2 text-[13px] font-medium transition-all duration-150',
              isActivePath(pathname, '/settings')
                ? 'bg-gray-900 text-white dark:bg-indigo-600 dark:text-white'
                : 'text-gray-500 hover:bg-gray-50 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800/60 dark:hover:text-white',
            )}
          >
            <Settings className="h-4 w-4 shrink-0 opacity-70" />
            Settings
          </Link>
        </div>

        <style>{`
          .scrollbar-thin::-webkit-scrollbar {
            width: 3px;
          }
          .scrollbar-thin::-webkit-scrollbar-track {
            background: transparent;
          }
          .scrollbar-thin::-webkit-scrollbar-thumb {
            background: #d1d5db;
            border-radius: 9999px;
          }
          .dark .scrollbar-thin::-webkit-scrollbar-thumb {
            background: #374151;
          }
          .scrollbar-thin::-webkit-scrollbar-thumb:hover {
            background: #9ca3af;
          }
          .dark .scrollbar-thin::-webkit-scrollbar-thumb:hover {
            background: #4b5563;
          }
        `}</style>
      </div>
    </>
  )
}
