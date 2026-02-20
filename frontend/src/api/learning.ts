import { apiClient } from './client'
import type { Lesson, ConversationAnalysis, LearningStats } from '../lib/types'

export async function getLessons(): Promise<{ lessons: Lesson[]; total: number }> {
  const { data } = await apiClient.get('/learning/lessons')
  return data
}

export async function getAnalyses(limit = 50): Promise<{ analyses: ConversationAnalysis[]; total: number }> {
  const { data } = await apiClient.get('/learning/analyses', { params: { limit } })
  return data
}

export async function getLearningStats(): Promise<LearningStats> {
  const { data } = await apiClient.get<LearningStats>('/learning/stats')
  return data
}

export async function triggerReflection(): Promise<{ status: string; message: string }> {
  const { data } = await apiClient.post('/learning/trigger-reflection')
  return data
}
