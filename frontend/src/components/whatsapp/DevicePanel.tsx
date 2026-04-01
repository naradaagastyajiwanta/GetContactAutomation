/**
 * DevicePanel Component — Redesigned
 *
 * Clean multi-device management with:
 * - Connected devices shown prominently with stats
 * - Disconnected/available slots shown as compact actionable rows
 * - Sleek QR code modal with connection progress
 */

import { useState, useEffect } from 'react'
import toast from 'react-hot-toast'
import {
  RefreshCw,
  QrCode,
  CheckCircle,
  XCircle,
  AlertCircle,
  Wifi,
  WifiOff,
  Phone,
  ArrowUpCircle,
  ArrowDownCircle,
  Loader2,
  Unplug,
  Link2,
  Smartphone,
  X,
} from 'lucide-react'
import {
  useWhatsAppDevices,
  useConnectDevice,
  useDisconnectDevice,
  useDeviceQR,
  useForceRecoverDevice,
} from '../../hooks/useWhatsApp'
import type { WhatsAppDevice } from '../../types/waDevices'
import { cn } from '../../lib/utils'

function formatRelativeTime(timestamp: number | null): string | null {
  if (!timestamp) {
    return null
  }

  const diffMs = Date.now() - timestamp
  const diffMinutes = Math.max(1, Math.round(diffMs / 60000))

  if (diffMinutes < 60) {
    return `${diffMinutes}m ago`
  }

  const diffHours = Math.round(diffMinutes / 60)
  if (diffHours < 24) {
    return `${diffHours}h ago`
  }

  const diffDays = Math.round(diffHours / 24)
  return `${diffDays}d ago`
}

function AuthRecoveryNotice({ device }: { device: WhatsAppDevice }) {
  const { authRecovery } = device
  const hasIssue = Boolean(authRecovery.lastIssue)
  const hasRecoveryHistory = authRecovery.authResetCount > 0 || Boolean(authRecovery.lastRecoveryAt)

  if (!hasIssue && !hasRecoveryHistory) {
    return null
  }

  const lastIssueAt = formatRelativeTime(authRecovery.lastIssueAt)
  const lastRecoveryAt = formatRelativeTime(authRecovery.lastRecoveryAt)
  const toneClass = authRecovery.recoveryRecommended
    ? 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200'
    : 'border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-900/20 dark:text-sky-200'

  return (
    <div className={cn('rounded-lg border px-3 py-2 text-xs', toneClass)}>
      <div className="flex items-start gap-2">
        <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <div className="min-w-0 space-y-1">
          <p className="font-semibold">
            {authRecovery.recoveryRecommended ? 'Auth issue needs attention' : 'Recent auth recovery activity'}
          </p>
          {authRecovery.lastIssue && <p className="leading-4">{authRecovery.lastIssue}</p>}
          <p className="text-[11px] opacity-80">
            {authRecovery.authResetCount > 0 ? `${authRecovery.authResetCount} recovery resets` : 'No recovery resets yet'}
            {lastRecoveryAt ? ` • last recovery ${lastRecoveryAt}` : ''}
            {lastIssueAt ? ` • last issue ${lastIssueAt}` : ''}
          </p>
        </div>
      </div>
    </div>
  )
}

export function DevicePanel() {
  const { data: devicesData, isLoading, error } = useWhatsAppDevices()
  const connectMutation = useConnectDevice()
  const disconnectMutation = useDisconnectDevice()
  const recoverMutation = useForceRecoverDevice()

  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null)
  const [showQr, setShowQr] = useState(false)
  const [disconnectingId, setDisconnectingId] = useState<string | null>(null)
  const [recoveringId, setRecoveringId] = useState<string | null>(null)

  const selectedDevice = devicesData?.devices.find((d) => d.id === selectedDeviceId)
  const { data: qrData } = useDeviceQR(selectedDeviceId || '')

  // Split devices by status
  const connectedDevices = devicesData?.devices.filter((d) => d.connectionState === 'connected') || []
  const connectingDevices = devicesData?.devices.filter((d) => d.connectionState === 'connecting') || []
  const availableDevices =
    devicesData?.devices.filter((d) => d.connectionState === 'disconnected' || d.connectionState === 'error') || []

  // Auto-close QR modal when device connects successfully
  useEffect(() => {
    if (qrData?.connected && showQr) {
      const name = qrData.phoneNumber || selectedDevice?.name || 'Device'
      const timer = setTimeout(() => {
        setShowQr(false)
        setSelectedDeviceId(null)
        toast.success(`${name} connected successfully!`, { duration: 3000, icon: '🟢' })
      }, 1200)
      return () => clearTimeout(timer)
    }
  }, [qrData?.connected, qrData?.phoneNumber, showQr, selectedDevice?.name])

  if (error) {
    return (
      <div className="text-center py-12">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-red-100 dark:bg-red-900/30 mb-4">
          <AlertCircle className="w-8 h-8 text-red-500" />
        </div>
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-2">Failed to Load Devices</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4 max-w-md mx-auto">
          Make sure the WhatsApp service is running on port 3100.
        </p>
        <code className="text-xs bg-gray-100 dark:bg-gray-900 px-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 inline-block font-mono text-gray-600 dark:text-gray-400">
          cd whatsapp-service &amp;&amp; npm run dev
        </code>
      </div>
    )
  }

  const handleConnectDevice = (deviceId: string) => {
    connectMutation.mutate(deviceId)
    setSelectedDeviceId(deviceId)
    setShowQr(true)
  }

  const handleDisconnect = (deviceId: string) => {
    setDisconnectingId(deviceId)
    disconnectMutation.mutate(deviceId, {
      onSettled: () => setDisconnectingId(null),
    })
    if (selectedDeviceId === deviceId) {
      setSelectedDeviceId(null)
      setShowQr(false)
    }
  }

  const handleShowQr = (deviceId: string) => {
    setSelectedDeviceId(deviceId)
    setShowQr(true)
  }

  const handleForceRecover = (deviceId: string) => {
    setRecoveringId(deviceId)
    recoverMutation.mutate(deviceId, {
      onSuccess: () => {
        setSelectedDeviceId(deviceId)
        setShowQr(true)
      },
      onSettled: () => setRecoveringId(null),
    })
  }

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <Loader2 className="w-10 h-10 animate-spin text-blue-500 mb-3" />
        <p className="text-sm text-gray-500 dark:text-gray-400">Loading devices...</p>
      </div>
    )
  }

  if (!devicesData?.devices || devicesData.devices.length === 0) {
    return (
      <div className="text-center py-16">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-gray-100 dark:bg-gray-700 mb-4">
          <Smartphone className="w-8 h-8 text-gray-400" />
        </div>
        <h3 className="text-lg font-bold text-gray-700 dark:text-gray-300 mb-2">No Devices Configured</h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Run the migration script to set up device slots.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* ── Connected Devices ─────────────────────────────── */}
      {connectedDevices.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <Wifi className="w-4 h-4 text-green-500" />
            <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              Connected ({connectedDevices.length})
            </h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {connectedDevices.map((device) => (
              <ConnectedDeviceCard
                key={device.id}
                device={device}
                onDisconnect={handleDisconnect}
                onForceRecover={handleForceRecover}
                isDisconnecting={disconnectingId === device.id}
                isRecovering={recoveringId === device.id}
              />
            ))}
          </div>
        </section>
      )}

      {/* ── Connecting Devices ────────────────────────────── */}
      {connectingDevices.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <Loader2 className="w-4 h-4 text-amber-500 animate-spin" />
            <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              Connecting ({connectingDevices.length})
            </h3>
          </div>
          <div className="space-y-2">
            {connectingDevices.map((device) => (
              <div
                key={device.id}
                className="flex items-center justify-between px-4 py-3 rounded-xl border-2 border-amber-200 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-900/10 transition-all"
              >
                <div className="flex items-center gap-3">
                  <div className="w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse" />
                  <span className="font-medium text-gray-900 dark:text-gray-100 text-sm">{device.name}</span>
                  <span className="text-xs text-amber-600 dark:text-amber-400 font-medium">Waiting for QR scan...</span>
                </div>
                <button
                  onClick={() => handleShowQr(device.id)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-amber-700 dark:text-amber-300 bg-amber-100 dark:bg-amber-900/30 hover:bg-amber-200 dark:hover:bg-amber-900/50 rounded-lg transition-colors border border-amber-300 dark:border-amber-700"
                >
                  <QrCode className="w-3.5 h-3.5" />
                  Show QR
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Available Device Slots ────────────────────────── */}
      {availableDevices.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <WifiOff className="w-4 h-4 text-gray-400" />
            <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              Available Slots ({availableDevices.length})
            </h3>
          </div>
          <div className="space-y-2">
            {availableDevices.map((device) => (
              <div
                key={device.id}
                className={cn(
                  'flex items-center justify-between px-4 py-3 rounded-xl border-2 transition-all group',
                  device.connectionState === 'error'
                    ? 'border-red-200 dark:border-red-800 bg-red-50/50 dark:bg-red-900/10'
                    : 'border-gray-200 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/50 hover:border-blue-300 dark:hover:border-blue-700 hover:bg-blue-50/30 dark:hover:bg-blue-900/10'
                )}
              >
                <div className="flex min-w-0 items-start gap-3">
                  <div
                    className={cn(
                      'w-2.5 h-2.5 rounded-full',
                      device.connectionState === 'error' ? 'bg-red-400' : 'bg-gray-300 dark:bg-gray-600'
                    )}
                  />
                  <div className="min-w-0 flex-1 space-y-2">
                    <span className="font-medium text-gray-900 dark:text-gray-100 text-sm">{device.name}</span>
                    {device.lastError && (
                      <p className="text-xs text-red-500 dark:text-red-400 mt-0.5 max-w-md truncate">{device.lastError}</p>
                    )}
                    <AuthRecoveryNotice device={device} />
                  </div>
                </div>
                <div className="ml-4 flex shrink-0 items-center gap-2 self-center">
                  {(device.authRecovery.recoveryRecommended || Boolean(device.authRecovery.lastIssue)) && (
                    <button
                      onClick={() => handleForceRecover(device.id)}
                      disabled={recoveringId === device.id}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/20 hover:bg-amber-100 dark:hover:bg-amber-900/40 border border-amber-200 dark:border-amber-800 rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {recoveringId === device.id ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <RefreshCw className="w-3.5 h-3.5" />
                      )}
                      Recover
                    </button>
                  )}
                  <button
                    onClick={() => handleConnectDevice(device.id)}
                    disabled={connectMutation.isPending}
                    className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20 hover:bg-blue-100 dark:hover:bg-blue-900/40 border border-blue-200 dark:border-blue-800 rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed group-hover:shadow-sm"
                  >
                    {connectMutation.isPending ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Link2 className="w-3.5 h-3.5" />
                    )}
                    Connect
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── QR Code Modal ─────────────────────────────────── */}
      {showQr && selectedDevice && (
        <QrModal
          device={selectedDevice}
          qrData={qrData}
          onClose={() => {
            setShowQr(false)
            setSelectedDeviceId(null)
          }}
        />
      )}
    </div>
  )
}

/* ─── Connected Device Card ──────────────────────────────── */

function ConnectedDeviceCard({
  device,
  onDisconnect,
  onForceRecover,
  isDisconnecting,
  isRecovering,
}: {
  device: WhatsAppDevice
  onDisconnect: (id: string) => void
  onForceRecover: (id: string) => void
  isDisconnecting: boolean
  isRecovering: boolean
}) {
  const [showConfirm, setShowConfirm] = useState(false)

  return (
    <div className="relative rounded-xl border-2 border-green-200 dark:border-green-800 bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/10 p-4 transition-all hover:shadow-md">
      {/* Animated status dot */}
      <div className="absolute top-3 right-3">
        <span className="relative flex h-3 w-3">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500" />
        </span>
      </div>

      {/* Device info */}
      <div className="mb-3">
        <h4 className="font-bold text-gray-900 dark:text-gray-100 text-sm">{device.name}</h4>
        {device.phoneNumber && (
          <div className="flex items-center gap-1.5 mt-1">
            <Phone className="w-3.5 h-3.5 text-green-600 dark:text-green-400" />
            <span className="text-sm font-semibold text-green-700 dark:text-green-300">{device.phoneNumber}</span>
          </div>
        )}
      </div>

      {/* Compact metrics row */}
      <div className="flex items-center gap-4 mb-3 text-xs">
        <div className="flex items-center gap-1 text-green-700 dark:text-green-300">
          <ArrowUpCircle className="w-3.5 h-3.5" />
          <span className="font-semibold">{device.metrics.messagesSent}</span>
          <span className="text-green-600/70 dark:text-green-400/70">sent</span>
        </div>
        <div className="flex items-center gap-1 text-red-600 dark:text-red-400">
          <ArrowDownCircle className="w-3.5 h-3.5" />
          <span className="font-semibold">{device.metrics.messagesFailed}</span>
          <span className="text-red-500/70 dark:text-red-400/70">failed</span>
        </div>
      </div>

      {(device.authRecovery.lastIssue || device.authRecovery.authResetCount > 0 || device.authRecovery.lastRecoveryAt) && (
        <div className="mb-3">
          <AuthRecoveryNotice device={device} />
        </div>
      )}

      <button
        onClick={() => onForceRecover(device.id)}
        disabled={isRecovering}
        className="mb-2 w-full flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-semibold text-amber-700 dark:text-amber-300 hover:text-amber-800 dark:hover:text-amber-200 bg-amber-50/80 dark:bg-amber-900/30 hover:bg-amber-100 dark:hover:bg-amber-900/40 border border-amber-200 dark:border-amber-800 rounded-lg transition-all disabled:opacity-50"
      >
        {isRecovering ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
        Force Recovery
      </button>

      {/* Disconnect with confirmation */}
      {!showConfirm ? (
        <button
          onClick={() => setShowConfirm(true)}
          className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-semibold text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400 bg-white/60 dark:bg-gray-800/60 hover:bg-red-50 dark:hover:bg-red-900/20 border border-gray-200 dark:border-gray-700 hover:border-red-200 dark:hover:border-red-800 rounded-lg transition-all"
        >
          <Unplug className="w-3.5 h-3.5" />
          Disconnect
        </button>
      ) : (
        <div className="flex gap-2">
          <button
            onClick={() => setShowConfirm(false)}
            className="flex-1 px-3 py-2 text-xs font-semibold text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => {
              onDisconnect(device.id)
              setShowConfirm(false)
            }}
            disabled={isDisconnecting}
            className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-bold text-white bg-red-500 hover:bg-red-600 rounded-lg transition-colors disabled:opacity-50"
          >
            {isDisconnecting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Unplug className="w-3.5 h-3.5" />}
            Confirm
          </button>
        </div>
      )}
    </div>
  )
}

/* ─── QR Code Modal ──────────────────────────────────────── */

function QrModal({
  device,
  qrData,
  onClose,
}: {
  device: WhatsAppDevice
  qrData: any
  onClose: () => void
}) {
  return (
    <div
      className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden">
        {/* Modal header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100 dark:border-gray-700">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
              <QrCode className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <h3 className="font-bold text-gray-900 dark:text-gray-100 text-base leading-tight">Scan QR Code</h3>
              <p className="text-xs text-gray-500 dark:text-gray-400">{device.name}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200" />
          </button>
        </div>

        {/* QR Content */}
        <div className="px-5 py-6">
          {qrData?.connected ? (
            /* ── Success state ── */
            <div className="text-center py-4">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-green-100 dark:bg-green-900/30 mb-3">
                <CheckCircle className="w-9 h-9 text-green-500" />
              </div>
              <h4 className="text-lg font-bold text-gray-900 dark:text-gray-100">Connected!</h4>
              {qrData.phoneNumber && (
                <p className="text-sm text-green-600 dark:text-green-400 font-semibold mt-1">{qrData.phoneNumber}</p>
              )}
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">Closing automatically...</p>
            </div>
          ) : qrData?.qr ? (
            /* ── QR Code display ── */
            <div className="text-center">
              <div className="inline-block p-3 bg-white rounded-2xl shadow-inner border border-gray-100 mb-4">
                <img src={qrData.qr} alt="QR Code" className="w-56 h-56" />
              </div>
              <div className="space-y-1.5">
                <p className="text-sm text-gray-600 dark:text-gray-300 font-medium">
                  Open WhatsApp <span className="text-gray-400 mx-0.5">→</span> Linked Devices <span className="text-gray-400 mx-0.5">→</span> Link a Device
                </p>
                <p className="text-xs text-gray-400 dark:text-gray-500">QR refreshes automatically</p>
              </div>
            </div>
          ) : (
            /* ── Loading state ── */
            <div className="text-center py-8">
              <Loader2 className="w-10 h-10 animate-spin text-blue-500 mx-auto mb-3" />
              <p className="text-sm font-medium text-gray-600 dark:text-gray-300">Generating QR code...</p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">This takes a few seconds</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
