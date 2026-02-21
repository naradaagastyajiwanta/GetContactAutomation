import { apiClient } from './client'

export interface KnowledgeItem {
  id: number
  chatbot_type: string
  title: string
  content: string
  situation_tags: string
  trigger_keywords: string
  is_active: number
  created_at: string
  updated_at: string
}

export async function getKnowledgeItems(
  chatbotType?: string,
): Promise<{ items: KnowledgeItem[] }> {
  const { data } = await apiClient.get('/knowledge-items', {
    params: chatbotType ? { chatbot_type: chatbotType } : undefined,
  })
  return data
}

export async function createKnowledgeItem(payload: {
  chatbot_type: string
  title: string
  content: string
  situation_tags?: string
  trigger_keywords?: string
}): Promise<{ id: number; status: string }> {
  const { data } = await apiClient.post('/knowledge-items', payload)
  return data
}

export async function updateKnowledgeItem(
  id: number,
  payload: { title?: string; content?: string; is_active?: boolean; situation_tags?: string; trigger_keywords?: string },
): Promise<{ status: string }> {
  const { data } = await apiClient.patch(`/knowledge-items/${id}`, payload)
  return data
}

export async function deleteKnowledgeItem(
  id: number,
): Promise<{ status: string }> {
  const { data } = await apiClient.delete(`/knowledge-items/${id}`)
  return data
}

export async function uploadKnowledgeFile(
  file: File,
  chatbotType: string,
): Promise<{ id: number; status: string; title: string; content_length: number }> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('chatbot_type', chatbotType)
  const { data } = await apiClient.post('/knowledge-items/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}
