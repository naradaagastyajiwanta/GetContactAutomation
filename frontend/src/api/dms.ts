import { apiClient } from './client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DmsStats {
  total_schedules: number
  upcoming_schedules: number
  today_schedules: number
  total_followups: number
  recent_followups_7d: number
  total_universities: number
  total_contacts: number
  total_auto_contacts: number
  approval_stats: Record<string, number>
  lsp_stats?: Record<string, number>
  source_counts?: Record<string, number>
}

export interface DmsSchedule {
  id: number
  source: 'schedule_follow_up' | 'schedule_follow_up_lsp'
  id_univ: number
  nama_universitas: string | null
  jadwal_audiensi: string | null
  jam_audensi: string | null
  type_meeting: string | null
  type_meetingdua: string | null
  link_zoom: string | null
  action: string | null
  status_approval: string | null
  est_audiens: number | null
  aktual_audiens: number | null
  notulen: string | null
  catatan: string | null
  catatan_marketing: string | null
  jenis_meetings: string | null
  alamat: string | null
  link_lokasi: string | null
  company_profile_link: string | null
  proposal_link: string | null
  surat_penawaran_link: string | null
  mou_link: string | null
  pks_link: string | null
  // LSP-specific fields (from detail view)
  meeting_topic?: string | null
  meeting_lembaga?: string | null
  passcode?: string | null
  tanggal_meeting?: string | null
  meeting_status?: string | null
  tanggal_schedule?: string | null
  zoom_meeting_id?: string | null
  lokasi?: string | null
}

export interface DmsPic {
  nama_pic: string | null
  jabatan_pic: string | null
  no_pic: string | null
}

export interface DmsScheduleDetail extends DmsSchedule {
  email_kampus: string | null
  alamat_universitas: string | null
  pics: DmsPic[]
  meetings: DmsMeeting[]
  // LSP detail fields
  id_lembaga?: number | null
  skema?: string | null
  namapimpinan?: string | null
  jabatanpic?: string | null
  est_mou?: string | null
  akt_mou?: string | null
  expired_mou?: string | null
  expired_moa?: string | null
  start_url?: string | null
  akun_zoom?: string | null
  host_key?: string | null
}

export interface DmsFollowup {
  id: number
  id_univ: number
  nama_universitas?: string | null
  metode_followup: number | null
  hasil_followup: number | null
  catatan: string | null
  tanggal_follow_up: string | null
  next_follow_up_date: string | null
  user_name?: string | null
}

export interface DmsMeeting {
  id: number
  meeting_id: string | null
  topic: string | null
  link_zoom: string | null
  passcode: string | null
  jadwal_meeting: string | null
  jam_meeting: string | null
  duration_minutes: number | null
}

export interface DmsUniversity {
  id_univ: number
  universitas: string
  email_kampus: string | null
  alamat: string | null
  contacts?: DmsUniversityContact[]
}

export interface DmsUniversityContact {
  id: number
  nama_kontak: string | null
  jabatan: string | null
  no_hp: string | null
  email: string | null
}

export interface DmsApproval {
  id: number
  id_followup: number
  status: string | null
  nama_universitas: string | null
  jadwal_audiensi: string | null
  created_at: string | null
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function getDmsHealth(): Promise<{ status: string; host: string; database: string }> {
  const { data } = await apiClient.get('/dms/health')
  return data
}

export async function getDmsStats(): Promise<DmsStats> {
  const { data } = await apiClient.get<DmsStats>('/dms/stats')
  return data
}

export async function getDmsSchedules(
  daysAhead: number = 30,
  includePastDays: number = 7,
): Promise<{ total: number; schedules: DmsSchedule[] }> {
  const { data } = await apiClient.get('/dms/schedules', {
    params: { days_ahead: daysAhead, include_past_days: includePastDays },
  })
  return data
}

export async function getDmsSchedulesToday(): Promise<{ total: number; schedules: DmsSchedule[] }> {
  const { data } = await apiClient.get('/dms/schedules/today')
  return data
}

export async function getDmsScheduleDetail(
  id: number,
  source: string = 'schedule_follow_up',
): Promise<DmsScheduleDetail> {
  const { data } = await apiClient.get<DmsScheduleDetail>(`/dms/schedules/${id}`, {
    params: { source },
  })
  return data
}

export async function getDmsFollowups(limit: number = 50): Promise<{ total: number; followups: DmsFollowup[] }> {
  const { data } = await apiClient.get('/dms/followups', { params: { limit } })
  return data
}

export async function getDmsFollowupsByUniversity(
  idUniv: number,
  limit: number = 20,
): Promise<{ total: number; followups: DmsFollowup[] }> {
  const { data } = await apiClient.get(`/dms/followups/${idUniv}`, { params: { limit } })
  return data
}

export async function getDmsMeetings(daysAhead: number = 14): Promise<{ total: number; meetings: DmsMeeting[] }> {
  const { data } = await apiClient.get('/dms/meetings', { params: { days_ahead: daysAhead } })
  return data
}

export async function searchDmsUniversities(
  q: string,
  limit: number = 20,
): Promise<{ total: number; universities: DmsUniversity[] }> {
  const { data } = await apiClient.get('/dms/universities/search', { params: { q, limit } })
  return data
}

export interface DmsPicResult {
  id_univ: number | null
  nama_universitas: string | null
  nama_pic: string | null
  jabatan_pic: string | null
  no_pic: string | null
  pic_source: string
}

export async function searchDmsPics(
  q: string = '',
  limit: number = 50,
): Promise<{ total: number; pics: DmsPicResult[] }> {
  const { data } = await apiClient.get('/dms/pics/search', { params: { q, limit } })
  return data
}

export async function getDmsUniversity(idUniv: number): Promise<DmsUniversity> {
  const { data } = await apiClient.get<DmsUniversity>(`/dms/universities/${idUniv}`)
  return data
}

export async function getDmsApprovals(
  status?: string,
  limit: number = 50,
): Promise<{ total: number; approvals: DmsApproval[] }> {
  const { data } = await apiClient.get('/dms/approvals', { params: { status, limit } })
  return data
}

export async function triggerContactSync(): Promise<{ status: string; message: string }> {
  const { data } = await apiClient.post('/dms/sync/contacts')
  return data
}

export async function triggerScheduleSync(): Promise<{ status: string; message: string }> {
  const { data } = await apiClient.post('/dms/sync/schedules')
  return data
}

// ---------------------------------------------------------------------------
// Research (SQLite — local GetContact DB)
// ---------------------------------------------------------------------------

export interface DmsResearchData {
  rector_name?: string | null
  rector_birth_year?: number | null
  rector_birth_city?: string | null
  rector_source?: string | null
  university_city?: string | null
  tourism_rector_birth_youth?: string | null
  tourism_rector_birth_youth_source?: string | null
  tourism_rector_birth_current?: string | null
  tourism_rector_birth_current_source?: string | null
  tourism_university_city?: string | null
  tourism_university_city_source?: string | null
  food_rector_birth_city?: string | null
  food_rector_birth_city_source?: string | null
  food_university_city?: string | null
  food_university_city_source?: string | null
  psychographics?: string | null
  psychographics_source?: string | null
  notes?: string | null
  // legacy flat sources list (older records)
  sources?: string[] | null
}

export interface DmsResearch {
  id?: number
  schedule_id: number
  source: string
  university_name: string | null
  university_city: string | null
  schedule_date: string | null
  researched_at: string | null
  research_data: DmsResearchData | null
}

export async function getDmsResearchResults(
  limit: number = 500,
): Promise<{ results: DmsResearch[]; count: number }> {
  const { data } = await apiClient.get('/dms/research/results', { params: { limit } })
  return data
}

export async function triggerResearchForSchedule(
  id: number,
  source: string,
): Promise<{ status: string; message: string }> {
  const { data } = await apiClient.post(`/dms/research/schedule/${id}`, null, {
    params: { source },
  })
  return data
}

export async function getDmsResearchBySchedule(
  scheduleId: number,
): Promise<{ status: string; data: DmsResearch | null }> {
  const { data } = await apiClient.get(`/dms/research/results/${scheduleId}`)
  return data
}
