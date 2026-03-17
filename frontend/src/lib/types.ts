export interface University {
  id: number
  name: string
  pddikti_id: string | null
  province: string | null
  website: string | null
  ig_handle: string | null
  ig_verified: boolean
  secretariat_phone: string | null
  email_kampus: string | null
  email_source: string | null
  rector_name: string | null
  student_count: number | null
  status: UniversityStatus
  enabled: boolean | number
  created_at: string
  updated_at?: string | null
  total_contacts?: number
  contacted_contacts?: number
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
  source_ig_handle: string | null
  source_ig_type: string | null
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
  manual_contacted: boolean
  conversation_state: string | null
  conversation_id: number | null
  created_at: string
}

export interface RelatedIg {
  id: number
  university_id: number
  ig_handle: string
  relation_type: string
  source: string
  confidence: number
  posts_scraped: boolean | number
  discovered_at: string
}

export interface Conversation {
  id: number
  university_id: number | null
  university_name?: string
  contact_phone: string
  state: ConversationState
  message_history: Message[]
  extracted_number: string | null
  extracted_contact_name?: string | null
  extracted_contact_role?: string | null
  last_message_at: string | null
  next_action_at: string | null
  attempt_count: number
  is_test?: boolean
  created_at: string
  agent_reasoning?: string | null
  linked_audiensi?: {
    id: number
    state: AudiensiState
    university_name?: string
    scheduled_datetime: string | null
    zoom_link: string | null
    created_at: string
  } | null
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

export interface RunningAgent {
  id: number
  agent_type: PipelineAgentType
  trigger_type: PipelineTriggerType
  started_at: string
  items_processed: number
  items_success: number
  target_count?: number
}

export interface PipelineStatus {
  pending: number
  ig_found: number
  ig_scraped: number
  contacted: number
  got_number: number
  failed: number
  running_agents?: RunningAgent[]
}

export interface ControlStatus {
  paused: boolean
  chatbot_enabled: boolean
  audiensi_enabled: boolean
  research_multi_agent: boolean
  reason?: string
}

export interface ApiKeyInfo {
  ok: boolean
  error: string | null
  configured: boolean
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
    total?: number
    healthy?: number
    sessions?: Array<{
      label: string
      ok: boolean
      error: string | null
    }>
    fallbacks?: {
      apify?: { configured: boolean; label: string }
      scrapingbot?: { configured: boolean; label: string }
    }
  }
  api_keys?: {
    serper: ApiKeyInfo
    apify: ApiKeyInfo
    scrapingbot: ApiKeyInfo
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

export interface AudiensiConversation {
  id: number
  university_id: number
  university_name?: string
  province?: string | null
  source_conversation_id: number | null
  contact_phone: string
  contact_role: string | null
  rector_name: string | null
  state: AudiensiState
  message_history: Message[]
  pdf_path: string | null
  initial_message_draft: string | null
  scheduled_datetime: string | null
  zoom_link: string | null
  agent_reasoning: string | null
  attempt_count: number
  followup_count: number
  approved_at: string | null
  approved_by: string | null
  created_at: string
  last_message_at: string | null
}

export type AudiensiState =
  | 'QUEUED'
  | 'APPROVED'
  | 'INITIAL_SENT'
  | 'WAITING_REPLY'
  | 'REPLIED'
  | 'ANALYZING'
  | 'SCHEDULING'
  | 'SCHEDULED'
  | 'ZOOM_SENT'
  | 'NEED_MORE'
  | 'FOLLOWUP_SENT'
  | 'REFUSED'
  | 'NO_REPLY'
  | 'ABANDONED'

export interface ApiCallLog {
  id: number
  conversation_id: number | null
  chatbot_type: 'agent' | 'audiensi'
  call_type: 'reply' | 'initial' | 'followup'
  situation_tags: string[]
  knowledge_items_injected: Array<{ id: number; title: string; tags: string }>
  system_prompt: string | null
  messages_sent: Array<{ role: string; content: string }> | null
  model_used: string | null
  tool_calls_made: string[]
  response_text: string | null
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cached_tokens: number
  created_at: string
}

export interface AudiensiStats {
  total: number
  queued: number
  approved: number
  in_progress: number
  scheduled: number
  completed: number
  refused: number
  abandoned: number
  state_counts: Record<string, number>
}

export type PipelineAgentType = 'find_handles' | 'scrape_posts' | 'extract_phones' | 'collect_universities' | 'discover_bem' | 'dms_research'
export type PipelineTriggerType = 'manual' | 'scheduler'
export type PipelineLogStatus = 'running' | 'completed' | 'failed'

export interface PipelineLog {
  id: number
  agent_type: PipelineAgentType
  trigger_type: PipelineTriggerType
  status: PipelineLogStatus
  started_at: string
  completed_at: string | null
  duration_seconds: number | null
  summary: Record<string, unknown> | null
  details: Array<Record<string, unknown>> | null
  error: string | null
  items_processed: number
  items_success: number
  items_failed: number
}
