import { useState, useRef, useEffect } from 'react'
import { Bell, CheckCheck, X, Wifi, WifiOff } from 'lucide-react'
import { useWebSocket } from '../../hooks/useWebSocket'
import { cn } from '../../lib/utils'
import { formatDistanceToNow } from 'date-fns'

const ICON_MAP: Record<string, string> = {
  'agent_completed': '✅',
  'got_number': '📞',
  'blast_completed': '🎉',
  'quota_reached': '⛔',
  'conversation_changed': '💬',
  'university_updated': '🏛',
}

export function NotificationCenter() {
  const { connected, notifications, unread, markRead, markAllRead, clear } = useWebSocket()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <div ref={ref} className="relative">
      {/* Bell button */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 transition-colors hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
        title={connected ? 'Notifications' : 'Notifications (offline)'}
      >
        <Bell className="h-5 w-5" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-indigo-500 text-[9px] font-bold text-white">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-80 rounded-xl border border-gray-200 bg-white shadow-xl dark:border-gray-700 dark:bg-gray-800">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3 dark:border-gray-700">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-gray-900 dark:text-white">Notifications</span>
              {unread > 0 && (
                <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-bold text-indigo-600 dark:bg-indigo-900/50 dark:text-indigo-300">
                  {unread} new
                </span>
              )}
            </div>
            <div className="flex items-center gap-1">
              {unread > 0 && (
                <button
                  onClick={markAllRead}
                  className="flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700"
                  title="Mark all as read"
                >
                  <CheckCheck className="h-3.5 w-3.5" />
                  Read all
                </button>
              )}
              <button
                onClick={() => setOpen(false)}
                className="rounded p-1 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Connection status */}
          <div className={cn(
            'flex items-center gap-1.5 border-b border-gray-100 px-4 py-2 text-[10px] dark:border-gray-700',
            connected ? 'text-emerald-600 dark:text-emerald-400' : 'text-gray-400'
          )}>
            {connected ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
            {connected ? 'Real-time updates active' : 'Reconnecting...'}
          </div>

          {/* List */}
          <div className="max-h-96 overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 text-center">
                <Bell className="h-8 w-8 text-gray-300 dark:text-gray-600" />
                <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">No notifications yet</p>
                <p className="text-[10px] text-gray-400 dark:text-gray-500">Events will appear here as they happen</p>
              </div>
            ) : (
              notifications.map((n) => (
                <div
                  key={n.id}
                  className={cn(
                    'group relative flex items-start gap-3 border-b border-gray-50 px-4 py-3 transition-colors dark:border-gray-800',
                    !n.read && 'bg-indigo-50/50 dark:bg-indigo-950/10',
                    'hover:bg-gray-50 dark:hover:bg-gray-700/30'
                  )}
                  onClick={() => markRead(n.id)}
                >
                  {/* Icon */}
                  <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-gray-100 text-sm dark:bg-gray-700">
                    {ICON_MAP[n.type] || '📌'}
                  </div>

                  {/* Content */}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-gray-900 dark:text-white">{n.title}</p>
                    {n.body && (
                      <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400 line-clamp-2">{n.body}</p>
                    )}
                    <p className="mt-1 text-[10px] text-gray-400 dark:text-gray-500">
                      {formatDistanceToNow(new Date(n.time), { addSuffix: true })}
                    </p>
                  </div>

                  {/* Unread dot + delete */}
                  <div className="flex flex-col items-center gap-2">
                    {!n.read && <div className="h-2 w-2 rounded-full bg-indigo-500" />}
                    <button
                      onClick={(e) => { e.stopPropagation(); clear(n.id) }}
                      className="opacity-0 group-hover:opacity-100"
                    >
                      <X className="h-3.5 w-3.5 text-gray-400 hover:text-gray-600" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
