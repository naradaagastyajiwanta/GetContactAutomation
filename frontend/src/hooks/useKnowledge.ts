import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  getKnowledgeItems,
  createKnowledgeItem,
  updateKnowledgeItem,
  deleteKnowledgeItem,
  uploadKnowledgeFile,
} from '../api/knowledge'
import { queryKeys } from '../lib/queryKeys'

export function useKnowledgeItems(chatbotType?: string) {
  return useQuery({
    queryKey: queryKeys.knowledge.list(chatbotType),
    queryFn: () => getKnowledgeItems(chatbotType),
  })
}

export function useCreateKnowledgeItem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createKnowledgeItem,
    onSuccess: () => {
      toast.success('Knowledge item created')
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.all })
    },
    onError: () => {
      toast.error('Failed to create knowledge item')
    },
  })
}

export function useUpdateKnowledgeItem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...payload }: { id: number; title?: string; content?: string; is_active?: boolean; situation_tags?: string; trigger_keywords?: string }) =>
      updateKnowledgeItem(id, payload),
    onSuccess: () => {
      toast.success('Knowledge item updated')
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.all })
    },
    onError: () => {
      toast.error('Failed to update knowledge item')
    },
  })
}

export function useDeleteKnowledgeItem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: deleteKnowledgeItem,
    onSuccess: () => {
      toast.success('Knowledge item deleted')
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.all })
    },
    onError: () => {
      toast.error('Failed to delete knowledge item')
    },
  })
}

export function useUploadKnowledgeFile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ file, chatbotType }: { file: File; chatbotType: string }) =>
      uploadKnowledgeFile(file, chatbotType),
    onSuccess: (data) => {
      toast.success(`File "${data.title}" uploaded (${data.content_length} chars)`)
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.all })
    },
    onError: (error: any) => {
      const detail = error?.response?.data?.detail
      toast.error(detail || 'Failed to upload file')
    },
  })
}
