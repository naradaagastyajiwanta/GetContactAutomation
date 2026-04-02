import { useState } from 'react'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { Wifi, Mail, CheckCircle2, Loader2 } from 'lucide-react'
import { useHandoffGroup } from '../../hooks/useMarketing'
import toast from 'react-hot-toast'
import { useNavigate } from 'react-router-dom'

interface MarketingHandoffModalProps {
  groupId: number
  waCount: number
  emailCount: number
  onClose: () => void
}

type ChannelType = 'wa_blast' | 'email_blast'

const STEPS = ['Pilih Channel', 'Preview', 'Konfirmasi'] as const

export function MarketingHandoffModal({
  groupId,
  waCount,
  emailCount,
  onClose,
}: MarketingHandoffModalProps) {
  const [step, setStep] = useState<0 | 1 | 2>(0)
  const [channel, setChannel] = useState<ChannelType>('wa_blast')
  const navigate = useNavigate()

  const handoffMutation = useHandoffGroup()

  async function handleConfirm() {
    try {
      const result = await handoffMutation.mutateAsync({ groupId, handoffType: channel })
      if (result.success && result.campaign_id) {
        toast.success('Berhasil membuat campaign blast')
        onClose()
        if (channel === 'wa_blast') {
          navigate(`/blast/${result.campaign_id}`)
        } else {
          navigate(`/email-blast/campaigns/${result.campaign_id}`)
        }
      } else {
        toast.error(result.message ?? 'Gagal membuat campaign')
      }
    } catch {
      toast.error('Gagal mengirim ke blast system')
    }
  }

  const loading = handoffMutation.isPending

  return (
    <Modal isOpen onClose={onClose} title="Kirim ke Blast" size="md">
      <div className="space-y-6">
        {/* Step indicator */}
        <div className="flex items-center gap-0">
          {STEPS.map((s, i) => (
            <div key={s} className="flex items-center">
              <div
                className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold transition-colors ${
                  i < step
                    ? 'bg-indigo-600 text-white'
                    : i === step
                    ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900 dark:text-indigo-300 ring-2 ring-indigo-500'
                    : 'bg-gray-100 text-gray-400 dark:bg-gray-700 dark:text-gray-500'
                }`}
              >
                {i < step ? <CheckCircle2 className="h-4 w-4" /> : i + 1}
              </div>
              <span
                className={`ml-2 text-sm font-medium ${
                  i <= step ? 'text-gray-900 dark:text-gray-100' : 'text-gray-400 dark:text-gray-500'
                }`}
              >
                {s}
              </span>
              {i < STEPS.length - 1 && (
                <div
                  className={`mx-3 h-px flex-1 ${
                    i < step ? 'bg-indigo-400' : 'bg-gray-200 dark:bg-gray-700'
                  }`}
                  style={{ minWidth: 24 }}
                />
              )}
            </div>
          ))}
        </div>

        {/* Step content */}
        {step === 0 && (
          <div className="space-y-3">
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Pilih channel blast yang akan digunakan untuk mengirim pesan ke kontak yang sudah
              di-approve dan di-select.
            </p>
            <div className="space-y-2">
              <ChannelOption
                selected={channel === 'wa_blast'}
                onClick={() => setChannel('wa_blast')}
                icon={Wifi}
                label="WA Blast"
                description="Kirim pesan WhatsApp ke kontak yang memiliki nomor WA"
                disabled={waCount === 0}
              />
              <ChannelOption
                selected={channel === 'email_blast'}
                onClick={() => setChannel('email_blast')}
                icon={Mail}
                label="Email Blast"
                description="Kirim email ke kontak yang memiliki alamat email"
                disabled={emailCount === 0}
              />
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-3">
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Pastikan data di bawah ini sudah benar sebelum melanjutkan.
            </p>
            <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-800">
              <table className="min-w-full text-sm">
                <tbody>
                  <tr className="divide-y divide-gray-200 dark:divide-gray-700">
                    <td className="py-2 text-gray-500 dark:text-gray-400">Channel</td>
                    <td className="py-2 font-medium text-gray-900 dark:text-gray-100">
                      {channel === 'wa_blast' ? 'WA Blast' : 'Email Blast'}
                    </td>
                  </tr>
                  <tr>
                    <td className="py-2 text-gray-500 dark:text-gray-400">Jumlah Kontak WA</td>
                    <td className="py-2 font-medium text-gray-900 dark:text-gray-100">{waCount}</td>
                  </tr>
                  <tr>
                    <td className="py-2 text-gray-500 dark:text-gray-400">Jumlah Kontak Email</td>
                    <td className="py-2 font-medium text-gray-900 dark:text-gray-100">{emailCount}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950">
              <p className="text-xs text-amber-700 dark:text-amber-300">
                Hanya kontak yang sudah di-approve dan di-select akan dikirimkan.
                Kontak yang belum di-approve akan tetap tersimpan dan bisa di-blast lain waktu.
              </p>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-3 text-center py-4">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-indigo-100 dark:bg-indigo-900/50">
              {channel === 'wa_blast'
                ? <Wifi className="h-6 w-6 text-indigo-600 dark:text-indigo-400" />
                : <Mail className="h-6 w-6 text-indigo-600 dark:text-indigo-400" />}
            </div>
            <div>
              <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Konfirmasi Kirim
              </p>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                {channel === 'wa_blast'
                  ? `${waCount} kontak WA akan dibuatkan campaign WA Blast baru`
                  : `${emailCount} kontak email akan dibuatkan campaign Email Blast baru`}
              </p>
            </div>
          </div>
        )}

        {/* Navigation */}
        <div className="flex justify-between gap-2 pt-2">
          <Button
            type="button"
            variant="secondary"
            onClick={() => (step === 0 ? onClose() : setStep((s) => (s - 1) as 0 | 1 | 2))}
            disabled={loading}
          >
            {step === 0 ? 'Batal' : 'Kembali'}
          </Button>
          {step < 2 ? (
            <Button onClick={() => setStep((s) => (s + 1) as 0 | 1 | 2)}>
              Lanjut
            </Button>
          ) : (
            <Button
              onClick={handleConfirm}
              loading={loading}
              disabled={loading}
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  <CheckCircle2 className="h-4 w-4" />
                  Konfirmasi & Kirim
                </>
              )}
            </Button>
          )}
        </div>
      </div>
    </Modal>
  )
}

function ChannelOption({
  selected,
  onClick,
  icon: Icon,
  label,
  description,
  disabled,
}: {
  selected: boolean
  onClick: () => void
  icon: React.ElementType
  label: string
  description: string
  disabled: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`w-full flex items-center gap-4 rounded-lg border-2 p-4 text-left transition-all ${
        selected
          ? 'border-indigo-500 bg-indigo-50 dark:border-indigo-400 dark:bg-indigo-950/50'
          : disabled
          ? 'border-gray-200 opacity-50 cursor-not-allowed dark:border-gray-700'
          : 'border-gray-200 hover:border-indigo-300 dark:border-gray-700 dark:hover:border-indigo-500'
      }`}
    >
      <div
        className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${
          selected
            ? 'bg-indigo-100 dark:bg-indigo-900/50'
            : 'bg-gray-100 dark:bg-gray-800'
        }`}
      >
        <Icon
          className={`h-5 w-5 ${selected ? 'text-indigo-600 dark:text-indigo-400' : 'text-gray-400'}`}
        />
      </div>
      <div>
        <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">{label}</p>
        <p className="text-xs text-gray-500 dark:text-gray-400">{description}</p>
      </div>
      {selected && (
        <CheckCircle2 className="ml-auto h-5 w-5 text-indigo-600 dark:text-indigo-400" />
      )}
    </button>
  )
}
