import { apiClient } from './client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UniversityGroup {
  id: number
  name: string
  description: string
  university_count: number
  created_at: string
  updated_at: string
}

export interface GroupMemberUniversity {
  id: number
  name: string
  province: string | null
  website: string | null
  ig_handle: string | null
  email_kampus: string | null
  student_count: number | null
  status: string
  enabled: boolean | number
  created_at: string
  updated_at: string
  added_at: string
  total_contacts: number
  contacted_contacts: number
}

export interface UniversityGroupDetail {
  id: number
  name: string
  description: string
  created_at: string
  updated_at: string
  universities: GroupMemberUniversity[]
}

// ---------------------------------------------------------------------------
// API Functions
// ---------------------------------------------------------------------------

export async function listUniversityGroups(): Promise<{ success: boolean; groups: UniversityGroup[] }> {
  const response = await apiClient.get<{ success: boolean; groups: UniversityGroup[] }>('/university-groups')
  return response.data
}

export async function createUniversityGroup(
  name: string,
  description: string = ''
): Promise<{ success: boolean; group: UniversityGroup }> {
  const response = await apiClient.post<{ success: boolean; group: UniversityGroup }>('/university-groups', {
    name,
    description,
  })
  return response.data
}

export async function getUniversityGroup(
  groupId: number
): Promise<{ success: boolean; group: UniversityGroupDetail }> {
  const response = await apiClient.get<{ success: boolean; group: UniversityGroupDetail }>(
    `/university-groups/${groupId}`
  )
  return response.data
}

export async function updateUniversityGroup(
  groupId: number,
  data: { name?: string; description?: string }
): Promise<{ success: boolean; group: UniversityGroup }> {
  const response = await apiClient.put<{ success: boolean; group: UniversityGroup }>(
    `/university-groups/${groupId}`,
    data
  )
  return response.data
}

export async function deleteUniversityGroup(groupId: number): Promise<{ success: boolean; message: string }> {
  const response = await apiClient.delete<{ success: boolean; message: string }>(
    `/university-groups/${groupId}`
  )
  return response.data
}

export async function addUniversitiesToGroup(
  groupId: number,
  universityIds: number[]
): Promise<{ success: boolean; added: number }> {
  const response = await apiClient.post<{ success: boolean; added: number }>(
    `/university-groups/${groupId}/universities/add`,
    { university_ids: universityIds }
  )
  return response.data
}

export async function removeUniversitiesFromGroup(
  groupId: number,
  universityIds: number[]
): Promise<{ success: boolean; removed: number }> {
  const response = await apiClient.post<{ success: boolean; removed: number }>(
    `/university-groups/${groupId}/universities/remove`,
    { university_ids: universityIds }
  )
  return response.data
}

export async function getGroupUniversityIds(
  groupId: number
): Promise<{ success: boolean; university_ids: number[] }> {
  const response = await apiClient.get<{ success: boolean; university_ids: number[] }>(
    `/university-groups/${groupId}/university-ids`
  )
  return response.data
}
