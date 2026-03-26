import { Wifi, Bot, MessageSquare, Video } from 'lucide-react'
import { Card } from '../ui/Card'
import { useControlStatus } from '../../hooks/useControl'
import { useHealth } from '../../hooks/useHealth'

interface StatusRowProps {
  icon: React.ReactNode
  label: string
  isOn: boolean
  isPaused?: boolean
  detail?: string
}

function StatusRow({ icon, label, isOn, isPaused, detail }: StatusRowProps) {
  const dotColor = isOn ? (isPaused ? 'bg-amber-400' : 'bg-emerald-400') : 'bg-gray-300 dark:bg-gray-600'
  const labelColor = isOn ? (isPaused ? 'text-amber-600 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400') : 'text-gray-400 dark:text-gray-500'
  const statusText = isPaused ? 'Paused' : isOn ? 'Active' : 'Off'

  return (
    <div className="flex items-center gap-3 py-2">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gray-50 dark:bg-gray-700/50">
        {icon}
      </div>
      <div className="flex-1">
        <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{label}</p>
        {detail && <p className="text-xs text-gray-400 dark:text-gray-500">{detail}</p>}
      </div>
      <div className="flex items-center gap-2">
        <span className={`text-xs font-semibold ${labelColor}`}>{statusText}</span>
        <div className={`h-2 w-2 rounded-full ${dotColor} ${isOn && !isPaused ? 'animate-pulse' : ''}`} />
      </div>
    </div>
  )
}

export function SystemStatus() {
  const { data: control } = useControlStatus()
  const { data: health } = useHealth()

  const waConnected = health?.whatsapp?.connected ?? false
  const paused = control?.paused ?? false
  const chatbotEnabled = control?.chatbot_enabled ?? true
  const audiensiEnabled = control?.audiensi_enabled ?? false

  return (
    <Card>
      <div className="border-b border-gray-100 px-5 py-3 dark:border-gray-800">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">System Status</h3>
      </div>
      <div className="divide-y divide-gray-100 px-5 py-1 dark:divide-gray-800">
        <StatusRow
          icon={<Wifi className="h-4 w-4 text-gray-500 dark:text-gray-400" />}
          label="WhatsApp"
          isOn={waConnected}
          detail={waConnected ? 'Baileys connected' : 'Not connected'}
        />
        <StatusRow
          icon={<Bot className="h-4 w-4 text-gray-500 dark:text-gray-400" />}
          label="Bot Automation"
          isOn={!paused}
          isPaused={paused}
          detail={paused ? 'Pipeline paused manually' : 'Processing queued items'}
        />
        <StatusRow
          icon={<MessageSquare className="h-4 w-4 text-gray-500 dark:text-gray-400" />}
          label="Contact Finder"
          isOn={chatbotEnabled}
          detail={chatbotEnabled ? 'AI chatbot enabled' : 'Chatbot disabled'}
        />
        <StatusRow
          icon={<Video className="h-4 w-4 text-gray-500 dark:text-gray-400" />}
          label="Audiensi"
          isOn={audiensiEnabled}
          detail={audiensiEnabled ? 'Research active' : 'Not scheduled'}
        />
      </div>
    </Card>
  )
}
