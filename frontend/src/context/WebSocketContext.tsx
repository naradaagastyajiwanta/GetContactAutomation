import { createContext, useContext, useEffect, ReactNode } from 'react'
import { useWebSocket } from '../hooks/useWebSocket'

interface WebSocketContextValue {
  connected: boolean
}

const WebSocketContext = createContext<WebSocketContextValue>({
  connected: false,
})

export function useWebSocketContext() {
  return useContext(WebSocketContext)
}

interface WebSocketProviderProps {
  children: ReactNode
}

export function WebSocketProvider({ children }: WebSocketProviderProps) {
  const { connected } = useWebSocket()

  return (
    <WebSocketContext.Provider value={{ connected }}>
      {children}
    </WebSocketContext.Provider>
  )
}
