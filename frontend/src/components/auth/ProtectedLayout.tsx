import { WebSocketProvider } from '../../context/WebSocketContext'
import { AppShell } from '../layout/AppShell'

export function ProtectedLayout() {
  return (
    <WebSocketProvider>
      <AppShell />
    </WebSocketProvider>
  )
}