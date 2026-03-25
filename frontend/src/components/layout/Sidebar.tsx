import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  Bot,
  LayoutDashboard,
  GitBranch,
  GraduationCap,
  MessageSquare,
  Video,
  CalendarClock,
  Smartphone,
  Megaphone,
  Mail,
  Lightbulb,
  BookOpen,
  UserSearch,
  ScrollText,
  Settings,
  ChevronRight,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '../../lib/utils'

// Re-export for MobileNav
export { NAV_SECTIONS }
export type { NavSection }

// ─── Types ───────────────────────────────────────────────────────────────────

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
}

interface NavSection {
  id: string
  label: string
  icon: LucideIcon
  items: NavItem[]
}

// ─── Navigation Structure ─────────────────────────────────────────────────────

const NAV_SECTIONS: NavSection[] = [
  {
    id: 'overview',
    label: 'Overview',
    icon: LayoutDashboard,
    items: [
      { to: '/', label: 'Dashboard', icon: LayoutDashboard },
      { to: '/pipeline', label: 'Pipeline', icon: GitBranch },
    ],
  },
  {
    id: 'outreach',
    label: 'Outreach',
    icon: GraduationCap,
    items: [
      { to: '/universities', label: 'Universities', icon: GraduationCap },
      { to: '/conversations', label: 'Conversations', icon: MessageSquare },
      { to: '/audiensi', label: 'Audiensi', icon: Video },
      { to: '/dms-schedules', label: 'Audiensi Schedules', icon: CalendarClock },
    ],
  },
  {
    id: 'broadcast',
    label: 'Broadcast',
    icon: Smartphone,
    items: [
      { to: '/whatsapp', label: 'WhatsApp', icon: Smartphone },
      { to: '/blast', label: 'WA Blast', icon: Megaphone },
      { to: '/email-blast', label: 'Email Blast', icon: Mail },
    ],
  },
  {
    id: 'ai-data',
    label: 'AI & Data',
    icon: Lightbulb,
    items: [
      { to: '/learning', label: 'Learning', icon: Lightbulb },
      { to: '/knowledge', label: 'Knowledge Base', icon: BookOpen },
      { to: '/crm', label: 'PIC Profiling', icon: UserSearch },
    ],
  },
  {
    id: 'system',
    label: 'System',
    icon: ScrollText,
    items: [
      { to: '/api-logs', label: 'API Logs', icon: ScrollText },
    ],
  },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function isActivePath(pathname: string, to: string): boolean {
  if (to === '/') return pathname === '/'
  return pathname.startsWith(to)
}

function getActiveSection(pathname: string): string | null {
  for (const section of NAV_SECTIONS) {
    for (const item of section.items) {
      if (isActivePath(pathname, item.to)) return section.id
    }
  }
  return null
}

// ─── Sidebar ───────────────────────────────────────────────────────────────

export function Sidebar() {
  const { pathname } = useLocation()
  const activeSection = getActiveSection(pathname)

  const [openSections, setOpenSections] = useState<Set<string>>(() => {
    const all = new Set(NAV_SECTIONS.map((s) => s.id))
    if (activeSection) all.delete(activeSection)
    return all
  })

  useEffect(() => {
    if (activeSection) {
      setOpenSections((prev) => {
        if (prev.has(activeSection)) return prev
        const next = new Set(prev)
        next.add(activeSection)
        return next
      })
    }
  }, [activeSection])

  function toggleSection(id: string) {
    setOpenSections((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <aside className="flex h-full w-[220px] shrink-0 flex-col bg-white dark:bg-[#111827]">
      {/* Brand */}
      <div className="flex h-14 items-center gap-2.5 border-b border-gray-100 px-5 dark:border-gray-800/80">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gray-900 dark:bg-indigo-600">
          <Bot className="h-4 w-4 text-white" />
        </div>
        <span className="text-sm font-semibold text-gray-900 dark:text-white">
          GetContact AI
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-3 overflow-y-auto px-3 py-4 scrollbar-thin">
        {NAV_SECTIONS.map((section, idx) => {
          const isOpen = openSections.has(section.id)
          const Icon = section.icon

          return (
            <div key={section.id}>
              {/* Section divider */}
              {idx > 0 && (
                <div className="mb-3 mt-1 border-t border-gray-100 dark:border-gray-800/80" />
              )}

              {/* Section header */}
              <button
                onClick={() => toggleSection(section.id)}
                className="mb-1 flex w-full items-center gap-2 px-2 text-[11px] font-semibold uppercase tracking-wider text-gray-400 transition-colors duration-150 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
              >
                <Icon className="h-3.5 w-3.5 opacity-50" />
                <span className="flex-1 text-left">{section.label}</span>
                <ChevronRight
                  className={cn(
                    'h-3 w-3 transition-transform duration-200',
                    isOpen && 'rotate-90',
                  )}
                />
              </button>

              {/* Items */}
              <div
                className={cn(
                  'overflow-hidden transition-all duration-250 ease-in',
                  isOpen ? 'max-h-64 opacity-100' : 'max-h-0 opacity-0',
                )}
              >
                {section.items.map((item) => {
                  const ItemIcon = item.icon
                  const active = isActivePath(pathname, item.to)

                  return (
                    <Link
                      key={item.to}
                      to={item.to}
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

      {/* Custom scrollbar styles injected via style tag */}
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
    </aside>
  )
}
