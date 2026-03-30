/**
 * EmailSettingsPanel — SMTP config, letter numbering, IMAP settings.
 */

import { useState, useEffect } from 'react'
import {
  Settings,
  Mail,
  Hash,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Save,
} from 'lucide-react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useLetterConfig, useUpdateLetterConfig, useTestSmtp } from '../../hooks/useEmailBlast'
import { Spinner } from '../ui/Spinner'
import { Button } from '../ui/Button'
import { toast } from 'react-hot-toast'

export function EmailSettingsPanel() {
  const [smtpStatus, setSmtpStatus] = useState<'idle' | 'testing' | 'ok' | 'error'>('idle')
  const [letterFormat, setLetterFormat] = useState('')
  const [letterNumber, setLetterNumber] = useState('')

  const { data: letterConfig, isLoading: letterLoading } = useLetterConfig()
  const updateLetterMutation = useUpdateLetterConfig()
  const testSmtpMutation = useTestSmtp()

  useEffect(() => {
    if (letterConfig) {
      setLetterFormat(letterConfig.format_template)
      setLetterNumber(String(letterConfig.last_number))
    }
  }, [letterConfig])

  async function handleTestSmtp() {
    setSmtpStatus('testing')
    try {
      const result = await testSmtpMutation.mutateAsync()
      if (result.success) {
        setSmtpStatus('ok')
        toast.success('SMTP connection successful')
      } else {
        setSmtpStatus('error')
        toast.error(result.message || 'SMTP connection failed')
      }
    } catch {
      setSmtpStatus('error')
      toast.error('SMTP connection failed')
    }
  }

  async function handleSaveLetter() {
    try {
      await updateLetterMutation.mutateAsync({
        format_template: letterFormat,
        last_number: parseInt(letterNumber) || 0,
      })
      toast.success('Letter config saved')
    } catch {
      toast.error('Failed to save')
    }
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-[#111827]">
        <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
          <Settings className="h-4 w-4" />
          <span>Email Settings</span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-5">
        <div className="max-w-lg space-y-8">
          {/* SMTP Test */}
          <section className="space-y-3">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white">
              <Mail className="h-4 w-4 text-gray-400" />
              SMTP Connection
            </h3>
            <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
              <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
                Test your SMTP connection to ensure emails can be sent.
              </p>
              <Button
                size="sm"
                variant="secondary"
                onClick={handleTestSmtp}
                loading={testSmtpMutation.isPending}
              >
                {smtpStatus === 'testing' ? (
                  <>
                    <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                    Testing...
                  </>
                ) : smtpStatus === 'ok' ? (
                  <>
                    <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
                    Connected
                  </>
                ) : smtpStatus === 'error' ? (
                  <>
                    <XCircle className="h-3.5 w-3.5 text-red-500" />
                    Failed — Retry
                  </>
                ) : (
                  <>
                    <RefreshCw className="h-3.5 w-3.5" />
                    Test Connection
                  </>
                )}
              </Button>
            </div>
          </section>

          {/* Letter Numbering */}
          <section className="space-y-3">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white">
              <Hash className="h-4 w-4 text-gray-400" />
              Letter Numbering
            </h3>
            <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800 space-y-4">
              {letterLoading ? (
                <div className="flex items-center justify-center py-4"><Spinner /></div>
              ) : (
                <>
                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-gray-600 dark:text-gray-400">
                      Format Template
                    </label>
                    <input
                      type="text"
                      value={letterFormat}
                      onChange={(e) => setLetterFormat(e.target.value)}
                      placeholder="{{NUMBER}}/ASOSIASI/{{YEAR}}"
                      className="w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm font-mono text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 dark:placeholder-gray-500"
                    />
                    <p className="mt-1 text-[10px] text-gray-400">
                      Variables: {"{{NUMBER}}"} (zero-padded), {"{{YEAR}}"}, {"{{MONTH}}"}, {"{{MONTH_NAME}}"}
                    </p>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-gray-600 dark:text-gray-400">
                      Last Number
                    </label>
                    <input
                      type="number"
                      value={letterNumber}
                      onChange={(e) => setLetterNumber(e.target.value)}
                      min={0}
                      className="w-32 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                    />
                  </div>

                  <Button
                    size="sm"
                    onClick={handleSaveLetter}
                    loading={updateLetterMutation.isPending}
                  >
                    <Save className="h-3.5 w-3.5" />
                    Save
                  </Button>
                </>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
