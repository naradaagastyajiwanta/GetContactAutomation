import { useWebSocketContext } from '../../context/WebSocketContext'
import { Bell, BellRing, Wifi, WifiOff } from 'lucide-react'
import { useState, useEffect } from 'react'
import { cn } from '../../lib/utils'

export function NotificationCenter() {
  const { connected } = useWebSocketContext()
  const [hasNew, setHasNew] = useState(false)

  // Reset indicator after 3 seconds
  useEffect(() => {
    if (hasNew) {
      const timeout = setTimeout(() => setHasNew(false), 3000)
      return () => clearTimeout(timeout)
    }
  }, [hasNew])

  // Show indicator when connection is established
  useEffect(() => {
    if (connected) {
      setHasNew(true)
    }
  }, [connected])

  return (
    <div className="flex items-center gap-2">
      {/* Connection status indicator */}
      <div
        className={cn(
          'flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium',
          connected
            ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
            : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
        )}
        title={connected ? 'Real-time updates active' : 'Real-time updates disconnected'}
      >
        {connected ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
        <span className="hidden sm:inline">
          {connected ? 'Live' : 'Polling'}
        </span>
      </div>

      {/* Notification bell */}
      <button
        className="relative p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        title={connected ? 'Notifications enabled' : 'Notifications disabled'}
      >
        {connected ? (
          <BellRing className="h-5 w-5 text-green-600 dark:text-green-400" />
        ) : (
          <Bell className="h-5 w-5 text-gray-400 dark:text-gray-500" />
        )}
        {hasNew && connected && (
          <span className="absolute top-1 right-1 h-2 w-2 bg-green-500 rounded-full animate-pulse" />
        )}
      </button>
    </div>
  )
}
