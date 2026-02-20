export interface University {
  id: number
  name: string
  pddikti_id: string | null
  province: string | null
  website: string | null
  ig_handle: string | null
  ig_verified: boolean
  secretariat_phone: string | null
  status: UniversityStatus
  created_at: string
}

export type UniversityStatus =
  | 'pending'
  | 'ig_found'
  | 'ig_scraped'
  | 'contacted'
  | 'got_number'
  | 'failed'

export interface IgPost {
  id: number
  university_id: number
  post_url: string
  image_url: string | null
  caption: string | null
  post_timestamp: string | null
  phone_extracted: boolean
  phones_found: number
  created_at: string
}

export interface IgContact {
  id: number
  university_id: number
  phone_number: string
  contact_name: string | null
  has_person_name: boolean
  source_post_url: string | null
  source_image_url: string | null
  created_at: string
}

export interface Conversation {
  id: number
  university_id: number | null
  university_name?: string
  contact_phone: string
  state: ConversationState
  message_history: Message[]
  extracted_number: string | null
  last_message_at: string | null
  next_action_at: string | null
  attempt_count: number
  is_test?: boolean
  created_at: string
  agent_reasoning?: string | null
}

export type ConversationState =
  | 'PENDING'
  | 'INITIAL_SENT'
  | 'WAITING_REPLY'
  | 'REPLIED'
  | 'ANALYZING'
  | 'GOT_NUMBER'
  | 'NEED_MORE'
  | 'FOLLOWUP_SENT'
  | 'REFUSED'
  | 'NO_REPLY'
  | 'ABANDONED'
  | 'UNDELIVERED'

export interface Message {
  role: 'bot' | 'contact'
  content: string
  timestamp: string
}

export interface DashboardStats {
  total_universities: number
  universities_with_ig: number
  universities_with_phone: number
  total_contacts: number
  total_conversations: number
  active_conversations: number
  successful_conversations: number
  today_messages_sent: number
  today_conversations_started: number
  daily_conversation_limit: number
}

export interface PipelineStatus {
  pending: number
  ig_found: number
  ig_scraped: number
  contacted: number
  got_number: number
  failed: number
}

export interface ControlStatus {
  paused: boolean
  reason?: string
}

export interface HealthStatus {
  status: string
  whatsapp: {
    connected: boolean
    [key: string]: unknown
  }
  instagram?: {
    ok: boolean
    error: string | null
  }
}

export interface Lesson {
  id: number
  situation_type: string
  insight: string
  recommended_strategy: string
  province: string | null
  success_rate: number
  example_count: number
  confidence: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface LearningStats {
  total_active_lessons: number
  unprocessed_analyses: number
  lessons_by_situation: Record<string, number>
}

export interface ConversationAnalysis {
  id: number
  conversation_id: number
  outcome: string
  total_messages: number
  total_attempts: number
  duration_hours: number
  province: string | null
  success_factors: string | null
  failure_factors: string | null
  contact_personality: string | null
  effective_strategies: string | null
  recommended_improvements: string | null
  summary: string | null
  processed: boolean
  created_at: string
}

export interface AgentResult {
  searched?: number
  found?: number
  scraped?: number
  total_posts?: number
  processed?: number
  phones_found?: number
  details?: Array<Record<string, unknown>>
}
