import { useState, useRef } from 'react'
import { BookOpen, Plus, Pencil, Trash2, Save, X, Upload } from 'lucide-react'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Spinner } from '../components/ui/Spinner'
import { EmptyState } from '../components/ui/EmptyState'
import { useAuth } from '../context/AuthContext'
import { useConfig, useUpdateConfig } from '../hooks/useConfig'
import {
  useKnowledgeItems,
  useCreateKnowledgeItem,
  useUpdateKnowledgeItem,
  useDeleteKnowledgeItem,
  useUploadKnowledgeFile,
} from '../hooks/useKnowledge'
import type { KnowledgeItem } from '../api/knowledge'

type ChatbotType = 'agent' | 'audiensi'

const TABS: { key: ChatbotType; label: string; configKey: string }[] = [
  { key: 'agent', label: 'Contact Finder', configKey: 'AGENT_CUSTOM_INSTRUCTIONS' },
  { key: 'audiensi', label: 'Audiensi', configKey: 'AUDIENSI_CUSTOM_INSTRUCTIONS' },
]

function CustomInstructionsEditor({ configKey }: { configKey: string }) {
  const { hasPermission } = useAuth()
  const { data: configData } = useConfig()
  const updateConfig = useUpdateConfig()
  const [localValue, setLocalValue] = useState<string | null>(null)
  const canManageSettings = hasPermission('settings.manage')

  const setting = configData?.settings.find((s) => s.key === configKey)
  const currentValue = localValue ?? (setting?.value as string) ?? ''
  const isDirty = localValue !== null && localValue !== (setting?.value as string ?? '')

  const handleSave = () => {
    if (localValue === null) return
    updateConfig.mutate({ [configKey]: localValue }, {
      onSuccess: () => setLocalValue(null),
    })
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
          Custom Instructions
        </label>
        {canManageSettings && isDirty && (
          <Button size="sm" onClick={handleSave} loading={updateConfig.isPending}>
            <Save className="h-3.5 w-3.5" />
            Save
          </Button>
        )}
      </div>
      <textarea
        value={currentValue}
        onChange={(e) => setLocalValue(e.target.value)}
        rows={4}
        disabled={!canManageSettings}
        placeholder="Tambahkan instruksi khusus untuk chatbot ini... (contoh: 'Selalu sebutkan nama lengkap organisasi')"
        className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 dark:placeholder-gray-500"
      />
      <p className="text-xs text-gray-500 dark:text-gray-400">
        Instruksi ini akan di-inject ke system prompt chatbot.
      </p>
      {!canManageSettings && (
        <p className="text-xs text-amber-600 dark:text-amber-300">
          Mengubah custom instructions membutuhkan permission settings.manage.
        </p>
      )}
    </div>
  )
}

function KnowledgeItemCard({
  item,
  onEdit,
  canManage,
}: {
  item: KnowledgeItem
  onEdit: () => void
  canManage: boolean
}) {
  const updateMutation = useUpdateKnowledgeItem()
  const deleteMutation = useDeleteKnowledgeItem()
  const [confirmDelete, setConfirmDelete] = useState(false)

  const handleToggle = () => {
    updateMutation.mutate({ id: item.id, is_active: !item.is_active })
  }

  const handleDelete = () => {
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }
    deleteMutation.mutate(item.id)
  }

  return (
    <div className="rounded-lg border border-gray-200 p-4 dark:border-gray-700">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {item.title}
            </h4>
            <span
              className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                item.is_active
                  ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                  : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
              }`}
            >
              {item.is_active ? 'Active' : 'Inactive'}
            </span>
          </div>
          {item.trigger_keywords && (
            <div className="mt-1 flex flex-wrap gap-1">
              {item.trigger_keywords.split(',').map((kw) => kw.trim()).filter(Boolean).map((kw) => (
                <span
                  key={kw}
                  className="inline-flex rounded bg-green-100 px-1.5 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400"
                >
                  {kw}
                </span>
              ))}
            </div>
          )}
          {item.situation_tags && (
            <div className="mt-1 flex flex-wrap gap-1">
              {item.situation_tags.split(',').map((tag) => tag.trim()).filter(Boolean).map((tag) => (
                <span
                  key={tag}
                  className="inline-flex rounded bg-indigo-100 px-1.5 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
          <p className="mt-1 text-sm text-gray-600 line-clamp-3 dark:text-gray-400">
            {item.content}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            onClick={handleToggle}
            disabled={updateMutation.isPending || !canManage}
            title={item.is_active ? 'Deactivate' : 'Activate'}
            className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
              item.is_active ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-600'
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
                item.is_active ? 'translate-x-4' : 'translate-x-0'
              }`}
            />
          </button>
          <button
            onClick={onEdit}
            disabled={!canManage}
            className="rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-700 dark:hover:text-gray-300"
            title="Edit"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={handleDelete}
            onBlur={() => setConfirmDelete(false)}
            disabled={deleteMutation.isPending || !canManage}
            className={`rounded p-1.5 transition-colors ${
              confirmDelete
                ? 'bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400'
                : 'text-gray-400 hover:bg-gray-100 hover:text-red-500 dark:hover:bg-gray-700'
            }`}
            title={confirmDelete ? 'Click again to confirm delete' : 'Delete'}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  )
}

function KnowledgeItemForm({
  chatbotType,
  editItem,
  onClose,
}: {
  chatbotType: ChatbotType
  editItem?: KnowledgeItem
  onClose: () => void
}) {
  const [title, setTitle] = useState(editItem?.title ?? '')
  const [content, setContent] = useState(editItem?.content ?? '')
  const [situationTags, setSituationTags] = useState(editItem?.situation_tags ?? '')
  const [triggerKeywords, setTriggerKeywords] = useState(editItem?.trigger_keywords ?? '')
  const createMutation = useCreateKnowledgeItem()
  const updateMutation = useUpdateKnowledgeItem()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim() || !content.trim()) return

    if (editItem) {
      updateMutation.mutate(
        { id: editItem.id, title: title.trim(), content: content.trim(), situation_tags: situationTags.trim(), trigger_keywords: triggerKeywords.trim() },
        { onSuccess: onClose },
      )
    } else {
      createMutation.mutate(
        { chatbot_type: chatbotType, title: title.trim(), content: content.trim(), situation_tags: situationTags.trim(), trigger_keywords: triggerKeywords.trim() },
        { onSuccess: onClose },
      )
    }
  }

  const isPending = createMutation.isPending || updateMutation.isPending

  return (
    <form onSubmit={handleSubmit} className="rounded-lg border border-indigo-200 bg-indigo-50/50 p-4 dark:border-indigo-800 dark:bg-indigo-950/20">
      <div className="space-y-3">
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Judul (contoh: 'Info Organisasi')"
          autoFocus
          className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 dark:placeholder-gray-500"
        />
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={3}
          placeholder="Isi pengetahuan..."
          className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 dark:placeholder-gray-500"
        />
        <div>
          <input
            type="text"
            value={triggerKeywords}
            onChange={(e) => setTriggerKeywords(e.target.value)}
            placeholder="Trigger keywords (pisahkan dengan koma, misal: kolaborasi, seperti apa, program)"
            className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 dark:placeholder-gray-500"
          />
          <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
            Kata kunci yang memicu inject item ini. Jika pesan kontak mengandung salah satu keyword, item akan di-inject ke system prompt.
          </p>
        </div>
        <div>
          <input
            type="text"
            value={situationTags}
            onChange={(e) => setSituationTags(e.target.value)}
            placeholder="Situation tags (opsional, misal: tone_umum)"
            className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 dark:placeholder-gray-500"
          />
          <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
            Tag 'tone_umum' = selalu di-inject tanpa perlu trigger keywords.
          </p>
        </div>
        <div className="flex items-center justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>
            <X className="h-3.5 w-3.5" />
            Cancel
          </Button>
          <Button
            type="submit"
            size="sm"
            loading={isPending}
            disabled={!title.trim() || !content.trim()}
          >
            <Save className="h-3.5 w-3.5" />
            {editItem ? 'Update' : 'Add'}
          </Button>
        </div>
      </div>
    </form>
  )
}

const ACCEPTED_FILE_TYPES = '.txt,.md,.csv,.docx,.pdf'

function FileUploadZone({ chatbotType, canManage }: { chatbotType: ChatbotType; canManage: boolean }) {
  const uploadMutation = useUploadKnowledgeFile()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  const handleFiles = (files: FileList | null) => {
    if (!canManage || !files) return
    for (let i = 0; i < files.length; i++) {
      uploadMutation.mutate({ file: files[i], chatbotType })
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    if (!canManage) return
    handleFiles(e.dataTransfer.files)
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        if (canManage) setDragOver(true)
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      onClick={() => canManage && fileInputRef.current?.click()}
      className={`rounded-lg border-2 border-dashed p-4 text-center transition-colors ${
        dragOver
          ? 'border-indigo-400 bg-indigo-50 dark:border-indigo-500 dark:bg-indigo-950/20'
          : canManage
            ? 'cursor-pointer border-gray-300 hover:border-gray-400 dark:border-gray-600 dark:hover:border-gray-500'
            : 'cursor-not-allowed border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800/50'
      }`}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_FILE_TYPES}
        multiple
        onChange={(e) => { handleFiles(e.target.files); e.target.value = '' }}
        disabled={!canManage}
        className="hidden"
      />
      <Upload className={`mx-auto h-6 w-6 ${dragOver ? 'text-indigo-500' : 'text-gray-400'}`} />
      <p className="mt-1.5 text-sm text-gray-600 dark:text-gray-400">
        {uploadMutation.isPending
          ? 'Uploading...'
          : canManage
            ? 'Drag & drop file atau klik untuk upload'
            : 'Upload file membutuhkan permission knowledge.manage'}
      </p>
      <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500">
        .txt, .md, .csv, .docx, .pdf (max 5MB)
      </p>
    </div>
  )
}

function ChatbotKBSection({ chatbotType, configKey }: { chatbotType: ChatbotType; configKey: string }) {
  const { hasPermission } = useAuth()
  const { data, isLoading } = useKnowledgeItems(chatbotType)
  const [showForm, setShowForm] = useState(false)
  const [editingItem, setEditingItem] = useState<KnowledgeItem | undefined>()
  const canManageKnowledge = hasPermission('knowledge.manage')

  const items = data?.items ?? []

  const handleEdit = (item: KnowledgeItem) => {
    setEditingItem(item)
    setShowForm(true)
  }

  const handleCloseForm = () => {
    setShowForm(false)
    setEditingItem(undefined)
  }

  return (
    <div className="space-y-6">
      {/* Custom Instructions */}
      <CustomInstructionsEditor configKey={configKey} />

      {/* Knowledge Items */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Knowledge Items
          </label>
          {canManageKnowledge && !showForm && (
            <Button size="sm" variant="secondary" onClick={() => { setEditingItem(undefined); setShowForm(true) }}>
              <Plus className="h-3.5 w-3.5" />
              Add Item
            </Button>
          )}
        </div>

        {/* File Upload Zone */}
        <div className="mb-3">
          <FileUploadZone chatbotType={chatbotType} canManage={canManageKnowledge} />
        </div>

        {canManageKnowledge && showForm && (
          <div className="mb-3">
            <KnowledgeItemForm
              chatbotType={chatbotType}
              editItem={editingItem}
              onClose={handleCloseForm}
            />
          </div>
        )}

        {isLoading ? (
          <div className="flex justify-center py-6">
            <Spinner />
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={BookOpen}
            title="Belum ada knowledge item"
            description="Tambahkan pengetahuan untuk membantu chatbot menjawab lebih baik."
          />
        ) : (
          <div className="space-y-2">
            {items.map((item) => (
              <KnowledgeItemCard
                key={item.id}
                item={item}
                canManage={canManageKnowledge}
                onEdit={() => handleEdit(item)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default function KnowledgeBasePage() {
  const [activeTab, setActiveTab] = useState<ChatbotType>('agent')

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
        Knowledge Base
      </h1>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-gray-100 p-1 dark:bg-gray-800">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? 'bg-white text-gray-900 shadow-sm dark:bg-gray-700 dark:text-gray-100'
                : 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-200'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <Card>
        {TABS.map((tab) =>
          activeTab === tab.key ? (
            <ChatbotKBSection
              key={tab.key}
              chatbotType={tab.key}
              configKey={tab.configKey}
            />
          ) : null,
        )}
      </Card>
    </div>
  )
}
