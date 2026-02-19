import { apiClient } from './client'
import type { Conversation, Message } from '../lib/types'

interface ConversationParams {
  state?: string
  limit?: number
  offset?: number
}

export async function getConversations(params?: ConversationParams): Promise<Conversation[]> {
  const { data } = await apiClient.get<Conversation[]>('/conversations', { params })
  return data
}

interface RawConversation extends Omit<Conversation, 'message_history'> {
  message_history: string | Message[]
}

export async function getConversation(id: number): Promise<Conversation> {
  const { data } = await apiClient.get<RawConversation>(`/conversations/${id}`)
  return {
    ...data,
    message_history:
      typeof data.message_history === 'string'
        ? JSON.parse(data.message_history)
        : data.message_history,
  }
}
