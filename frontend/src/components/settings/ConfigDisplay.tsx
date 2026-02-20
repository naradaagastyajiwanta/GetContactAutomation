import { useState, useEffect } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card'
import { useConfig, useUpdateConfig, useResetConfig, useModels } from '../../hooks/useConfig'
import { Spinner } from '../ui/Spinner'
import type { ConfigSetting } from '../../api/config'
import { RotateCcw, Save, Eye, EyeOff, CheckCircle, XCircle } from 'lucide-react'

function groupSettings(settings: ConfigSetting[]): Record<string, ConfigSetting[]> {
  const groups: Record<string, ConfigSetting[]> = {}
  for (const s of settings) {
    if (!groups[s.group]) groups[s.group] = []
    groups[s.group].push(s)
  }
  return groups
}

function SensitiveInput({
  setting,
  value,
  onChange,
}: {
  setting: ConfigSetting
  value: string
  onChange: (val: string) => void
}) {
  const [show, setShow] = useState(false)
  const [editing, setEditing] = useState(false)
  const [localVal, setLocalVal] = useState('')

  const handleStartEdit = () => {
    setEditing(true)
    setLocalVal('')
  }

  const handleConfirm = () => {
    if (localVal) {
      onChange(localVal)
    }
    setEditing(false)
  }

  const handleCancel = () => {
    setEditing(false)
    setLocalVal('')
  }

  if (editing) {
    return (
      <div className="flex items-center gap-1.5">
        <input
          type={show ? 'text' : 'password'}
          value={localVal}
          onChange={(e) => setLocalVal(e.target.value)}
          placeholder="Enter new value..."
          autoFocus
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleConfirm()
            if (e.key === 'Escape') handleCancel()
          }}
          className="w-56 rounded-md border border-blue-400 bg-white px-3 py-1.5 text-sm text-gray-900 dark:border-blue-500 dark:bg-gray-700 dark:text-gray-100"
        />
        <button
          type="button"
          onClick={() => setShow(!show)}
          className="rounded p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
        >
          {show ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
        </button>
        <button
          onClick={handleConfirm}
          className="rounded p-1 text-green-500 hover:text-green-600"
          title="Confirm"
        >
          <CheckCircle className="h-4 w-4" />
        </button>
        <button
          onClick={handleCancel}
          className="rounded p-1 text-red-400 hover:text-red-500"
          title="Cancel"
        >
          <XCircle className="h-4 w-4" />
        </button>
      </div>
    )
  }

  const hasValue = setting.has_value

  return (
    <div className="flex items-center gap-2">
      {hasValue ? (
        <code className="max-w-[10rem] truncate rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-700 dark:text-gray-400">
          {value}
        </code>
      ) : (
        <span className="text-sm italic text-gray-400 dark:text-gray-500">not set</span>
      )}
      <button
        onClick={handleStartEdit}
        className="shrink-0 rounded bg-gray-100 px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
      >
        {hasValue ? 'Change' : 'Set'}
      </button>
    </div>
  )
}

function ModelSelect({
  value,
  onChange,
}: {
  value: string
  onChange: (val: string) => void
}) {
  const { data, isLoading } = useModels()
  const models = data?.models ?? []

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-56 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
    >
      {isLoading && <option value={value}>{value} (loading...)</option>}
      {!isLoading && models.length === 0 && <option value={value}>{value}</option>}
      {models.map((m) => (
        <option key={m} value={m}>{m}</option>
      ))}
      {!isLoading && models.length > 0 && !models.includes(value) && (
        <option value={value}>{value} (current)</option>
      )}
    </select>
  )
}

function SettingInput({
  setting,
  value,
  onChange,
}: {
  setting: ConfigSetting
  value: string | number | boolean
  onChange: (val: string | number | boolean) => void
}) {
  if (setting.sensitive) {
    return (
      <SensitiveInput
        setting={setting}
        value={value as string}
        onChange={onChange}
      />
    )
  }

  if (setting.key === 'AGENT_MODEL') {
    return <ModelSelect value={value as string} onChange={onChange} />
  }

  if (setting.type === 'bool') {
    return (
      <button
        type="button"
        role="switch"
        aria-checked={!!value}
        onClick={() => onChange(!value)}
        className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
          value ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'
        }`}
      >
        <span
          className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow ring-0 transition-transform ${
            value ? 'translate-x-5' : 'translate-x-0'
          }`}
        />
      </button>
    )
  }

  if (setting.type === 'int' || setting.type === 'float') {
    return (
      <input
        type="number"
        value={value as number}
        step={setting.type === 'float' ? '0.1' : '1'}
        min={setting.min_value ?? undefined}
        max={setting.max_value ?? undefined}
        onChange={(e) => {
          const v = setting.type === 'float' ? parseFloat(e.target.value) : parseInt(e.target.value, 10)
          if (!isNaN(v)) onChange(v)
        }}
        className="w-32 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
      />
    )
  }

  return (
    <input
      type="text"
      value={value as string}
      onChange={(e) => onChange(e.target.value)}
      className="w-48 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
    />
  )
}

export function ConfigDisplay() {
  const { data, isLoading, error } = useConfig()
  const updateMutation = useUpdateConfig()
  const resetMutation = useResetConfig()

  const [localValues, setLocalValues] = useState<Record<string, string | number | boolean>>({})
  const [dirty, setDirty] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (data?.settings) {
      const vals: Record<string, string | number | boolean> = {}
      for (const s of data.settings) {
        // For sensitive fields, don't put the masked value into local state
        // since the user will enter a brand-new value when editing
        vals[s.key] = s.value
      }
      setLocalValues(vals)
      setDirty(new Set())
    }
  }, [data])

  if (isLoading) {
    return (
      <Card>
        <CardHeader><CardTitle>Configuration</CardTitle></CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8"><Spinner /></div>
        </CardContent>
      </Card>
    )
  }

  if (error || !data) {
    return (
      <Card>
        <CardHeader><CardTitle>Configuration</CardTitle></CardHeader>
        <CardContent>
          <p className="text-sm text-red-500">Failed to load configuration.</p>
        </CardContent>
      </Card>
    )
  }

  const groups = groupSettings(data.settings)

  const handleChange = (key: string, value: string | number | boolean) => {
    setLocalValues((prev) => ({ ...prev, [key]: value }))
    setDirty((prev) => new Set(prev).add(key))
  }

  const handleSave = () => {
    const changes: Record<string, string | number | boolean> = {}
    for (const key of dirty) {
      changes[key] = localValues[key]
    }
    if (Object.keys(changes).length === 0) return
    updateMutation.mutate(changes, {
      onSuccess: () => setDirty(new Set()),
    })
  }

  const handleReset = (key: string) => {
    resetMutation.mutate(key)
  }

  const isDefault = (setting: ConfigSetting) => {
    if (setting.sensitive) return !setting.has_value && !dirty.has(setting.key)
    return localValues[setting.key] === setting.default && !dirty.has(setting.key)
  }

  return (
    <Card padding={false}>
      <div className="p-6 pb-0">
        <div className="mb-4 flex items-center justify-between">
          <CardTitle>Configuration</CardTitle>
          {dirty.size > 0 && (
            <button
              onClick={handleSave}
              disabled={updateMutation.isPending}
              className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              <Save className="h-4 w-4" />
              {updateMutation.isPending ? 'Saving...' : `Save (${dirty.size})`}
            </button>
          )}
        </div>
      </div>

      <div className="divide-y divide-gray-200 dark:divide-gray-700">
        {Object.entries(groups).map(([group, settings]) => (
          <div key={group} className="px-6 py-4">
            <h4 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
              {group}
            </h4>
            <div className="space-y-3">
              {settings.map((setting) => (
                <div
                  key={setting.key}
                  className="flex items-center justify-between gap-4"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {setting.label}
                      </span>
                      {setting.sensitive && setting.has_value && !dirty.has(setting.key) && (
                        <span className="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700 dark:bg-green-900/30 dark:text-green-400">
                          set
                        </span>
                      )}
                      {setting.sensitive && !setting.has_value && !dirty.has(setting.key) && (
                        <span className="rounded bg-red-100 px-1.5 py-0.5 text-xs text-red-700 dark:bg-red-900/30 dark:text-red-400">
                          not set
                        </span>
                      )}
                      {dirty.has(setting.key) && (
                        <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                          modified
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {setting.description}
                      {setting.min_value != null && setting.max_value != null && (
                        <span className="ml-1">
                          ({setting.min_value} - {setting.max_value})
                        </span>
                      )}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <SettingInput
                      setting={setting}
                      value={localValues[setting.key] ?? setting.value}
                      onChange={(v) => handleChange(setting.key, v)}
                    />
                    {!setting.sensitive && !isDefault(setting) && (
                      <button
                        onClick={() => handleReset(setting.key)}
                        disabled={resetMutation.isPending}
                        title={`Reset to default (${setting.default})`}
                        className="rounded p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                      >
                        <RotateCcw className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}
