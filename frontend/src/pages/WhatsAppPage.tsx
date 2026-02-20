import { useState } from 'react'
import {
  Smartphone,
  QrCode,
  Send,
  LogOut,
  RefreshCw,
  Wifi,
  WifiOff,
} from 'lucide-react'
import { useWaQr, useWaStatus, useSendTestMessage, useWaLogout, useWaRestart } from '../hooks/useWhatsApp'
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Spinner } from '../components/ui/Spinner'
import { cn } from '../lib/utils'

export default function WhatsAppPage() {
  const { data: qrData, isLoading: qrLoading } = useWaQr()
  const { data: statusData } = useWaStatus()
  const sendTest = useSendTestMessage()
  const logout = useWaLogout()
  const restart = useWaRestart()

  const [testPhone, setTestPhone] = useState('')
  const [testMessage, setTestMessage] = useState('')
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false)

  const connected = qrData?.connected ?? false
  const phoneNumber = qrData?.phoneNumber ?? statusData?.phoneNumber ?? null
  const reconnectAttempt = statusData?.reconnectAttempt ?? 0
  const maxReconnect = statusData?.maxReconnectAttempts ?? 15

  const handleSendTest = () => {
    if (!testPhone.trim() || !testMessage.trim()) return
    sendTest.mutate(
      { to: testPhone.trim(), message: testMessage.trim() },
      { onSuccess: () => { setTestPhone(''); setTestMessage('') } },
    )
  }

  const handleLogout = () => {
    logout.mutate()
    setShowLogoutConfirm(false)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          WhatsApp Connection
        </h1>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => restart.mutate()}
          loading={restart.isPending}
        >
          <RefreshCw className="h-4 w-4" />
          Restart
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Connection Status */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Smartphone className="h-5 w-5 text-gray-500 dark:text-gray-400" />
              <CardTitle>Connection Status</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                {connected ? (
                  <Wifi className="h-8 w-8 text-green-500" />
                ) : (
                  <WifiOff className="h-8 w-8 text-red-400" />
                )}
                <div>
                  <p className={cn(
                    'text-lg font-semibold',
                    connected
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-red-600 dark:text-red-400',
                  )}>
                    {connected ? 'Connected' : 'Disconnected'}
                  </p>
                  {phoneNumber && (
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      Phone: +{phoneNumber}
                    </p>
                  )}
                </div>
              </div>

              {!connected && reconnectAttempt > 0 && (
                <div className="rounded-lg bg-yellow-50 p-3 dark:bg-yellow-900/20">
                  <p className="text-sm text-yellow-800 dark:text-yellow-200">
                    Reconnecting... attempt {reconnectAttempt}/{maxReconnect}
                  </p>
                  <div className="mt-2 h-1.5 rounded-full bg-yellow-200 dark:bg-yellow-800">
                    <div
                      className="h-1.5 rounded-full bg-yellow-500 transition-all"
                      style={{ width: `${Math.min((reconnectAttempt / maxReconnect) * 100, 100)}%` }}
                    />
                  </div>
                </div>
              )}

              <div className="flex gap-2 pt-2">
                {connected ? (
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => setShowLogoutConfirm(true)}
                    loading={logout.isPending}
                  >
                    <LogOut className="h-4 w-4" />
                    Logout
                  </Button>
                ) : (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => restart.mutate()}
                    loading={restart.isPending}
                  >
                    <RefreshCw className="h-4 w-4" />
                    Reconnect
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* QR Code */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <QrCode className="h-5 w-5 text-gray-500 dark:text-gray-400" />
              <CardTitle>QR Code</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col items-center justify-center py-4">
              {qrLoading ? (
                <Spinner size="lg" />
              ) : connected ? (
                <div className="text-center">
                  <Wifi className="mx-auto h-16 w-16 text-green-500" />
                  <p className="mt-3 text-sm font-medium text-green-600 dark:text-green-400">
                    WhatsApp is connected
                  </p>
                  {phoneNumber && (
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      +{phoneNumber}
                    </p>
                  )}
                </div>
              ) : qrData?.dataUrl ? (
                <div className="text-center">
                  <img
                    src={qrData.dataUrl}
                    alt="WhatsApp QR Code"
                    className="mx-auto h-64 w-64 rounded-lg border border-gray-200 dark:border-gray-600"
                  />
                  <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">
                    Scan with WhatsApp to connect
                  </p>
                </div>
              ) : (
                <div className="text-center">
                  <Spinner size="md" />
                  <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">
                    Waiting for QR code...
                  </p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Test Message */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Send className="h-5 w-5 text-gray-500 dark:text-gray-400" />
            <CardTitle>Send Test Message</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                Phone Number
              </label>
              <input
                type="text"
                value={testPhone}
                onChange={(e) => setTestPhone(e.target.value)}
                placeholder="e.g. 081234567890 or 6281234567890"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 dark:placeholder-gray-400"
                disabled={!connected}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                Message
              </label>
              <textarea
                value={testMessage}
                onChange={(e) => setTestMessage(e.target.value)}
                placeholder="Type your test message..."
                rows={3}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 dark:placeholder-gray-400"
                disabled={!connected}
              />
            </div>
            <Button
              onClick={handleSendTest}
              loading={sendTest.isPending}
              disabled={!connected || !testPhone.trim() || !testMessage.trim()}
              size="sm"
            >
              <Send className="h-4 w-4" />
              Send Test Message
            </Button>
            {!connected && (
              <p className="text-xs text-gray-400 dark:text-gray-500">
                Connect WhatsApp first to send messages.
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Logout Confirmation Modal */}
      {showLogoutConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="mx-4 w-full max-w-sm rounded-lg bg-white p-6 shadow-xl dark:bg-gray-800">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Logout from WhatsApp?
            </h3>
            <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
              This will disconnect the current WhatsApp session. You'll need to scan a new QR code to reconnect.
            </p>
            <div className="mt-4 flex justify-end gap-3">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowLogoutConfirm(false)}
              >
                Cancel
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={handleLogout}
                loading={logout.isPending}
              >
                Logout
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
