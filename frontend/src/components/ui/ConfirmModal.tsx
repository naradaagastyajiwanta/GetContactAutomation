import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { X, AlertTriangle } from 'lucide-react'
import { cn } from '../../lib/utils'
import { Button } from './Button'

interface ConfirmModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  variant?: 'danger' | 'default'
  loading?: boolean
}

export function ConfirmModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'default',
  loading = false,
}: ConfirmModalProps) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (isOpen) {
      // Small delay for enter animation
      requestAnimationFrame(() => setVisible(true))
    } else {
      setVisible(false)
    }
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [isOpen, onClose])

  if (!isOpen) return null

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className={cn(
          'fixed inset-0 bg-black/50 transition-opacity duration-200',
          visible ? 'opacity-100' : 'opacity-0'
        )}
        onClick={onClose}
      />

      {/* Modal */}
      <div
        className={cn(
          'relative w-full max-w-sm rounded-xl bg-white p-6 shadow-2xl dark:bg-gray-800',
          'transition-all duration-200',
          visible ? 'scale-100 opacity-100' : 'scale-95 opacity-0'
        )}
      >
        {/* Close */}
        <button
          onClick={onClose}
          className="absolute right-4 top-4 rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-700 dark:hover:text-gray-300"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Icon + Title */}
        <div className="mb-4 flex items-start gap-3 pr-6">
          <div className={cn(
            'mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full',
            variant === 'danger'
              ? 'bg-red-100 dark:bg-red-900/30'
              : 'bg-indigo-100 dark:bg-indigo-900/30'
          )}>
            <AlertTriangle className={cn(
              'h-5 w-5',
              variant === 'danger'
                ? 'text-red-600 dark:text-red-400'
                : 'text-indigo-600 dark:text-indigo-400'
            )} />
          </div>
          <div>
            <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">{title}</h3>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{message}</p>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={onClose}
            disabled={loading}
          >
            {cancelLabel}
          </Button>
          <Button
            size="sm"
            variant={variant === 'danger' ? 'danger' : 'primary'}
            onClick={onConfirm}
            loading={loading}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
