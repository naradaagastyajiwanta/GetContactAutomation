import { apiClient } from './client'

export interface PhoneNumber {
  id: number
  phone_number: string
  contact_name: string | null
  source_post_url: string | null
  source_image_url: string | null
  created_at: string
  university_id: number | null
  university_name: string | null
  province: string | null
}

export interface PaginatedPhoneNumbers {
  data: PhoneNumber[]
  total: number
}

export interface PhoneNumberStats {
  total_count: number
  today_count: number
  yesterday_count: number
  percent_change: number
}

export interface PhoneNumberParams {
  search?: string
  province?: string
  university_search?: string
  limit?: number
  offset?: number
  sort_by?: string
  order?: string
}

export async function getPhoneNumbers(params?: PhoneNumberParams): Promise<PaginatedPhoneNumbers> {
  const { data } = await apiClient.get<PaginatedPhoneNumbers>('/phone-numbers', { params })
  return data
}

export async function getPhoneNumberStats(): Promise<PhoneNumberStats> {
  const { data } = await apiClient.get<PhoneNumberStats>('/phone-numbers/stats')
  return data
}
