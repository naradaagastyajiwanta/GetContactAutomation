/**
 * EmailComposeBox — Gmail-style compose panel (inline).
 */

import { useState, useEffect } from 'react'
import {
  X,
  Send,
  Save,
  Eye,
  Paperclip,
  ChevronDown,
} from 'lucide-react'
import { cn } from '../../lib/utils'
import { Button } from '../ui/Button'
import type { EmailBlastCampaign } from '../../api/emailBlast'

interface Props {
  campaign?: EmailBlastCampaign
  onClose: () => void
  onSend?: () => void
  onSave?: () => void
}

export function EmailComposeBox({ campaign, onClose, onSave, onSend }: Props) {
  const [subject, setSubject] = useState(campaign?.subject ?? '')
  const [body, setBody] = useState(campaign?.template_message ?? '')
  const [showPreview, setShowPreview] = useState(false)

  useEffect(() => {
    if (campaign) {
      setSubject(campaign.subject)
      setBody(campaign.template_message)
    }
  }, [campaign])

  function insertPlaceholder(placeholder: string) {
    setBody((prev) => prev + placeholder)
  }

  const placeholders = [
    '{{university_name}}',
    '{{email}}',
    '{{tanggal}}',
    '{{nomor_surat}}',
  ]

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-900">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3 dark:border-gray-800">
        <span className="text-sm font-semibold text-gray-900 dark:text-white">
          {campaign ? 'Edit Campaign' : 'New Campaign'}
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowPreview(!showPreview)}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300"
            title="Preview"
          >
            <Eye className="h-4 w-4" />
          </button>
          <button
            onClick={onClose}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Form */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {/* Subject */}
        <div>
          <input
            type="text"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Subject"
            className="w-full border-0 border-b border-gray-100 bg-transparent px-0 py-2 text-sm font-medium text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-0 dark:border-gray-800 dark:text-gray-100"
          />
        </div>

        {/* Placeholder chips */}
        <div className="flex flex-wrap gap-1">
          {placeholders.map((p) => (
            <button
              key={p}
              onClick={() => insertPlaceholder(p)}
              className="rounded-md border border-gray-200 bg-gray-50 px-2 py-0.5 text-[10px] font-mono text-gray-500 hover:border-indigo-300 hover:text-indigo-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400"
            >
              {p}
            </button>
          ))}
        </div>

        {/* Body */}
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Email body..."
          rows={10}
          className="w-full resize-none rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-800 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
        />

        {/* Preview */}
        {showPreview && (
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-800">
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-gray-400">
              Preview (with sample values)
            </p>
            <div className="space-y-1 text-xs text-gray-600 dark:text-gray-300">
              <p>
                <span className="font-medium">Subject: </span>
                {subject.replace('{{university_name}}', 'Universitas Gadjah Mada')}
              </p>
              <div className="whitespace-pre-wrap leading-relaxed text-[11px]">
                {body
                  .replace(/{{university_name}}/g, 'Universitas Gadjah Mada')
                  .replace(/{{email}}/g, 'rektor@ugm.ac.id')
                  .replace(/{{tanggal}}/g, '15 April 2025')
                  .replace(/{{nomor_surat}}/g, '001/ASOSIASI/2025')}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between border-t border-gray-100 px-4 py-3 dark:border-gray-800">
        <button className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
          <Paperclip className="h-3.5 w-3.5" />
          Attach
        </button>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={onSave}>
            <Save className="h-3.5 w-3.5" />
            Save
          </Button>
          <Button size="sm" onClick={onSend}>
            <Send className="h-3.5 w-3.5" />
            Send
          </Button>
        </div>
      </div>
    </div>
  )
}
