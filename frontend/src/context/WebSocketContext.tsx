import { createContext, useContext, ReactNode } from 'react'
import { useWebSocket } from '../hooks/useWebSocket'
import type { Notification } from '../hooks/useNotifications'

interface WebSocketContextValue {
  connected: boolean
  notifications: Notification[]
  unreadCount: number
  markRead: (id: string) => void
  markAllRead: () => void
  clearNotification: (id: string) => void
}

const WebSocketContext = createContext<WebSocketContextValue>({
  connected: false,
  notifications: [],
  unreadCount: 0,
  markRead: () => {},
  markAllRead: () => {},
  clearNotification: () => {},
})

export function useWebSocketContext() {
  return useContext(WebSocketContext)
}

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const ws = useWebSocket()

  return (
    <WebSocketContext.Provider value={{
      connected: ws.connected,
      notifications: ws.notifications,
      unreadCount: ws.unread,
      markRead: ws.markRead,
      markAllRead: ws.markAllRead,
      clearNotification: ws.clear,
    }}>
      {children}
    </WebSocketContext.Provider>
  )
}
