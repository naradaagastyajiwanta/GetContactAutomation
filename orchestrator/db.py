import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import aiosqlite
import phonenumbers

from orchestrator.config import DATABASE_PATH, log, cfg
from orchestrator.websocket import manager as ws_manager

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS universities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    pddikti_id TEXT UNIQUE,
    province TEXT,
    website TEXT,
    ig_handle TEXT,
    ig_verified BOOLEAN DEFAULT 0,
    secretariat_phone TEXT,
    email_kampus TEXT,
    email_source TEXT,
    rector_name TEXT,
    student_count INTEGER DEFAULT NULL,
    status TEXT DEFAULT 'pending',
    enabled BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ig_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER REFERENCES universities(id),
    phone_number TEXT NOT NULL,
    contact_name TEXT,
    source_post_url TEXT,
    source_image_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ig_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER NOT NULL REFERENCES universities(id),
    post_url TEXT NOT NULL,
    image_url TEXT,
    caption TEXT,
    post_timestamp TEXT,
    phone_extracted BOOLEAN DEFAULT 0,
    phones_found INTEGER DEFAULT 0,
    source_ig_handle TEXT,
    source_ig_type TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(university_id, post_url)
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER REFERENCES universities(id),
    contact_phone TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'PENDING',
    message_history TEXT DEFAULT '[]',
    extracted_number TEXT,
    extracted_contact_name TEXT,
    extracted_contact_role TEXT,
    last_message_at TIMESTAMP,
    next_action_at TIMESTAMP,
    attempt_count INTEGER DEFAULT 0,
    followup_count INTEGER DEFAULT 0,
    is_test BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_quota (
    date TEXT PRIMARY KEY,
    messages_sent INTEGER DEFAULT 0,
    conversations_started INTEGER DEFAULT 0
);
"""

_DDL_AGENT = """
CREATE TABLE IF NOT EXISTS conversation_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER,
    outcome TEXT,
    total_messages INTEGER,
    total_attempts INTEGER,
    duration_hours REAL,
    province TEXT,
    success_factors TEXT,
    failure_factors TEXT,
    contact_personality TEXT,
    effective_strategies TEXT,
    recommended_improvements TEXT,
    summary TEXT,
    source TEXT DEFAULT 'outreach',
    processed INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    situation_type TEXT,
    insight TEXT,
    recommended_strategy TEXT,
    province TEXT,
    success_rate REAL DEFAULT 0,
    example_count INTEGER DEFAULT 0,
    confidence REAL DEFAULT 0.5,
    is_active INTEGER DEFAULT 1,
    source_analysis_ids TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS strategy_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER,
    strategy_used TEXT,
    situation_type TEXT,
    outcome TEXT,
    province TEXT,
    response_time_minutes REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_ig_contacts_unique
    ON ig_contacts(university_id, phone_number);

CREATE INDEX IF NOT EXISTS idx_ig_posts_extraction ON ig_posts(phone_extracted);
CREATE INDEX IF NOT EXISTS idx_ig_posts_university ON ig_posts(university_id);
CREATE INDEX IF NOT EXISTS idx_universities_status ON universities(status);
CREATE INDEX IF NOT EXISTS idx_conversations_phone ON conversations(contact_phone);
"""

_DDL_CONFIG = """
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);
"""

_DDL_AUTH = """
CREATE TABLE IF NOT EXISTS auth_user_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dms_user_id INTEGER NOT NULL,
    user_email TEXT NOT NULL,
    user_name TEXT NOT NULL,
    role_key TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    granted_by_email TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(dms_user_id, role_key)
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    session_hash TEXT PRIMARY KEY,
    dms_user_id INTEGER NOT NULL,
    user_email TEXT NOT NULL,
    user_name TEXT NOT NULL,
    dms_user_level TEXT,
    expires_at TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    last_seen_at TEXT DEFAULT (datetime('now')),
    revoked_at TEXT,
    user_agent TEXT,
    ip_address TEXT
);

CREATE TABLE IF NOT EXISTS auth_audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    actor_dms_user_id INTEGER,
    actor_email TEXT,
    subject_dms_user_id INTEGER,
    subject_email TEXT,
    role_key TEXT,
    success INTEGER DEFAULT 1,
    detail TEXT,
    ip_address TEXT,
    user_agent TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS auth_role_upgrade_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requester_dms_user_id INTEGER NOT NULL,
    requester_email TEXT NOT NULL,
    requester_name TEXT NOT NULL,
    current_role_key TEXT NOT NULL,
    requested_role_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    request_note TEXT,
    reviewed_by_dms_user_id INTEGER,
    reviewed_by_email TEXT,
    review_note TEXT,
    reviewed_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
"""

_INDEXES_AGENT = """
CREATE INDEX IF NOT EXISTS idx_conv_analyses_conv_id ON conversation_analyses(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conv_analyses_processed ON conversation_analyses(processed);
CREATE INDEX IF NOT EXISTS idx_lessons_situation ON lessons(situation_type);
CREATE INDEX IF NOT EXISTS idx_lessons_active ON lessons(is_active);
CREATE INDEX IF NOT EXISTS idx_strategy_metrics_conv ON strategy_metrics(conversation_id);
CREATE INDEX IF NOT EXISTS idx_strategy_metrics_strategy ON strategy_metrics(strategy_used);
"""

_INDEXES_AUTH = """
CREATE INDEX IF NOT EXISTS idx_auth_user_roles_user ON auth_user_roles(dms_user_id);
CREATE INDEX IF NOT EXISTS idx_auth_user_roles_email ON auth_user_roles(user_email);
CREATE INDEX IF NOT EXISTS idx_auth_user_roles_active ON auth_user_roles(is_active);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(dms_user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry ON auth_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_auth_audit_logs_action ON auth_audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_auth_audit_logs_actor_email ON auth_audit_logs(actor_email);
CREATE INDEX IF NOT EXISTS idx_auth_audit_logs_subject_email ON auth_audit_logs(subject_email);
CREATE INDEX IF NOT EXISTS idx_auth_audit_logs_created_at ON auth_audit_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_auth_role_upgrade_requests_requester ON auth_role_upgrade_requests(requester_dms_user_id);
CREATE INDEX IF NOT EXISTS idx_auth_role_upgrade_requests_status ON auth_role_upgrade_requests(status);
CREATE INDEX IF NOT EXISTS idx_auth_role_upgrade_requests_created_at ON auth_role_upgrade_requests(created_at);
"""

_DDL_AUDIENSI = """
CREATE TABLE IF NOT EXISTS audiensi_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER NOT NULL REFERENCES universities(id),
    source_conversation_id INTEGER REFERENCES conversations(id),
    contact_phone TEXT NOT NULL,
    contact_role TEXT,
    rector_name TEXT,
    state TEXT NOT NULL DEFAULT 'QUEUED',
    message_history TEXT DEFAULT '[]',
    pdf_path TEXT,
    initial_message_draft TEXT,
    scheduled_datetime TEXT,
    zoom_link TEXT,
    agent_reasoning TEXT,
    attempt_count INTEGER DEFAULT 0,
    followup_count INTEGER DEFAULT 0,
    last_message_at TIMESTAMP,
    approved_at TIMESTAMP,
    approved_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_DDL_KNOWLEDGE = """
CREATE TABLE IF NOT EXISTS knowledge_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chatbot_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    situation_tags TEXT DEFAULT '',
    trigger_keywords TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_INDEXES_KNOWLEDGE = """
CREATE INDEX IF NOT EXISTS idx_knowledge_items_type_active
    ON knowledge_items(chatbot_type, is_active);
"""

_INDEXES_AUDIENSI = """
CREATE INDEX IF NOT EXISTS idx_audiensi_phone ON audiensi_conversations(contact_phone);
CREATE INDEX IF NOT EXISTS idx_audiensi_state ON audiensi_conversations(state);
CREATE INDEX IF NOT EXISTS idx_audiensi_university ON audiensi_conversations(university_id);
"""

_DDL_API_LOGS = """
CREATE TABLE IF NOT EXISTS api_call_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER,
    chatbot_type TEXT NOT NULL,
    call_type TEXT NOT NULL DEFAULT 'reply',
    situation_tags TEXT DEFAULT '[]',
    knowledge_items_injected TEXT DEFAULT '[]',
    system_prompt TEXT,
    messages_sent TEXT,
    model_used TEXT,
    tool_calls_made TEXT DEFAULT '[]',
    response_text TEXT,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    cached_tokens INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_INDEXES_API_LOGS = """
CREATE INDEX IF NOT EXISTS idx_api_logs_conv_id ON api_call_logs(conversation_id);
CREATE INDEX IF NOT EXISTS idx_api_logs_chatbot_type ON api_call_logs(chatbot_type);
CREATE INDEX IF NOT EXISTS idx_api_logs_created_at ON api_call_logs(created_at);
"""

_DDL_PIPELINE_LOGS = """
CREATE TABLE IF NOT EXISTS pipeline_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_type TEXT NOT NULL,
    trigger_type TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL DEFAULT 'running',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    duration_seconds REAL,
    summary TEXT,
    details TEXT,
    error TEXT,
    items_processed INTEGER DEFAULT 0,
    items_success INTEGER DEFAULT 0,
    items_failed INTEGER DEFAULT 0
);
"""

_INDEXES_PIPELINE_LOGS = """
CREATE INDEX IF NOT EXISTS idx_pipeline_logs_agent_type ON pipeline_logs(agent_type);
CREATE INDEX IF NOT EXISTS idx_pipeline_logs_status ON pipeline_logs(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_logs_started_at ON pipeline_logs(started_at);
"""

_DDL_RELATED_IGS = """
CREATE TABLE IF NOT EXISTS university_related_igs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER NOT NULL REFERENCES universities(id),
    ig_handle TEXT NOT NULL,
    relation_type TEXT NOT NULL DEFAULT 'bem',
    source TEXT DEFAULT 'following',
    confidence REAL DEFAULT 0.0,
    posts_scraped BOOLEAN DEFAULT 0,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(university_id, ig_handle)
);
"""

_INDEXES_RELATED_IGS = """
CREATE INDEX IF NOT EXISTS idx_related_igs_university ON university_related_igs(university_id);
CREATE INDEX IF NOT EXISTS idx_related_igs_scraped ON university_related_igs(posts_scraped);
CREATE INDEX IF NOT EXISTS idx_related_igs_type ON university_related_igs(relation_type);
"""

_DDL_IG_ACCOUNTS = """
CREATE TABLE IF NOT EXISTS ig_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    enabled BOOLEAN DEFAULT 1,
    notes TEXT DEFAULT '',
    login_status TEXT DEFAULT 'untested',
    last_login_test TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_DDL_BLAST = """
CREATE TABLE IF NOT EXISTS blast_campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    template_message TEXT NOT NULL DEFAULT '',
    device_id TEXT DEFAULT 'device_1',
    delay_between_ms INTEGER DEFAULT 5000,
    human_delay_min_ms INTEGER DEFAULT 2000,
    human_delay_max_ms INTEGER DEFAULT 8000,
    content_variation_enabled INTEGER DEFAULT 1,
    schedule_enabled INTEGER DEFAULT 1,
    schedule_timezone TEXT DEFAULT 'Asia/Jakarta',
    active_hours_start INTEGER DEFAULT 8,
    active_hours_end INTEGER DEFAULT 21,
    peak_hours_start INTEGER DEFAULT 10,
    peak_hours_end INTEGER DEFAULT 14,
    lunch_break_start INTEGER DEFAULT 12,
    lunch_break_end INTEGER DEFAULT 13,
    weekend_factor REAL DEFAULT 0.5,
    auto_resume_enabled INTEGER DEFAULT 1,
    auto_resume_at TIMESTAMP,
    paused_reason TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    total_recipients INTEGER DEFAULT 0,
    sent_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    created_by_dms_user_id INTEGER,
    created_by_email TEXT,
    created_by_name TEXT,
    started_by_dms_user_id INTEGER,
    started_by_email TEXT,
    started_by_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    paused_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS blast_recipients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL REFERENCES blast_campaigns(id) ON DELETE CASCADE,
    contact_id INTEGER REFERENCES ig_contacts(id),
    university_id INTEGER REFERENCES universities(id),
    phone_number TEXT NOT NULL,
    contact_name TEXT,
    university_name TEXT,
    rendered_message TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(campaign_id, phone_number)
);
"""

_INDEXES_BLAST = """
CREATE INDEX IF NOT EXISTS idx_blast_campaigns_status ON blast_campaigns(status);
CREATE INDEX IF NOT EXISTS idx_blast_campaigns_owner ON blast_campaigns(created_by_dms_user_id);
CREATE INDEX IF NOT EXISTS idx_blast_campaigns_auto_resume ON blast_campaigns(auto_resume_at);
CREATE INDEX IF NOT EXISTS idx_blast_recipients_campaign ON blast_recipients(campaign_id);
CREATE INDEX IF NOT EXISTS idx_blast_recipients_status ON blast_recipients(status);
"""

# ---------------------------------------------------------------------------
# Email Blast Tables
# ---------------------------------------------------------------------------

_DDL_EMAIL_BLAST = """
CREATE TABLE IF NOT EXISTS email_blast_campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    template_message TEXT NOT NULL DEFAULT '',
    from_email TEXT NOT NULL DEFAULT 'sekretariat@asosiasi.ai',
    from_name TEXT NOT NULL DEFAULT 'Sekretariat Asosiasi AI',
    delay_between_ms INTEGER DEFAULT 8000,
    status TEXT NOT NULL DEFAULT 'draft',
    total_recipients INTEGER DEFAULT 0,
    sent_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    invalid_count INTEGER DEFAULT 0,
    attachment_filename TEXT,
    attachment_variables TEXT,
    created_by_dms_user_id INTEGER,
    created_by_email TEXT,
    created_by_name TEXT,
    started_by_dms_user_id INTEGER,
    started_by_email TEXT,
    started_by_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    paused_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS email_blast_recipients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL REFERENCES email_blast_campaigns(id) ON DELETE CASCADE,
    university_id INTEGER REFERENCES universities(id),
    email TEXT NOT NULL,
    university_name TEXT,
    rendered_subject TEXT,
    rendered_message TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(campaign_id, email)
);

-- Email Blast Daily Quota
CREATE TABLE IF NOT EXISTS email_blast_daily_quota (
    quota_date TEXT NOT NULL PRIMARY KEY,
    sent_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_email_quota_date ON email_blast_daily_quota(quota_date);

-- Letter Number Config
CREATE TABLE IF NOT EXISTS email_blast_letter_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    format_template TEXT NOT NULL DEFAULT '{{NUMBER}}/ASOSIASI/{{YEAR}}',
    last_number INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS email_inbox_cache (
    cache_key TEXT PRIMARY KEY,
    mailbox_email TEXT NOT NULL,
    uid INTEGER NOT NULL,
    sort_ts INTEGER NOT NULL DEFAULT 0,
    message_id TEXT,
    in_reply_to TEXT,
    from_email TEXT,
    from_name TEXT,
    to_email TEXT,
    subject TEXT,
    body TEXT,
    date TEXT,
    is_read INTEGER DEFAULT 0,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_inbox_cache_fetched ON email_inbox_cache(fetched_at DESC);

-- All outgoing emails (campaign + test)
CREATE TABLE IF NOT EXISTS email_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER REFERENCES email_blast_campaigns(id),
    recipient_id INTEGER REFERENCES email_blast_recipients(id),
    source TEXT NOT NULL DEFAULT 'campaign',  -- 'campaign' or 'test'
    email TEXT NOT NULL,
    university_name TEXT,
    from_email TEXT,
    from_name TEXT,
    rendered_subject TEXT,
    rendered_message TEXT,
    status TEXT NOT NULL DEFAULT 'sent',  -- 'sent', 'failed'
    error_message TEXT,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_outbox_sent_at ON email_outbox(sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_outbox_campaign ON email_outbox(campaign_id);

-- Cache for IMAP Sent folder
CREATE TABLE IF NOT EXISTS email_sent_cache (
    cache_key TEXT PRIMARY KEY,
    mailbox_email TEXT NOT NULL,
    uid INTEGER NOT NULL,
    sort_ts INTEGER NOT NULL DEFAULT 0,
    message_id TEXT,
    from_email TEXT,
    from_name TEXT,
    to_email TEXT,
    subject TEXT,
    body TEXT,
    date TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sent_cache_fetched ON email_sent_cache(fetched_at DESC);
"""

_INDEXES_EMAIL_BLAST = """
CREATE INDEX IF NOT EXISTS idx_email_blast_campaigns_status ON email_blast_campaigns(status);
CREATE INDEX IF NOT EXISTS idx_email_blast_campaigns_owner ON email_blast_campaigns(created_by_dms_user_id);
CREATE INDEX IF NOT EXISTS idx_email_blast_recipients_campaign ON email_blast_recipients(campaign_id);
CREATE INDEX IF NOT EXISTS idx_email_blast_recipients_status ON email_blast_recipients(status);
"""

# ---------------------------------------------------------------------------
# OSINT Tables
# ---------------------------------------------------------------------------

_DDL_OSINT = """
CREATE TABLE IF NOT EXISTS osint_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER NOT NULL REFERENCES universities(id),
    address TEXT,
    city TEXT,
    province TEXT,
    postal_code TEXT,
    phone_official TEXT,
    fax TEXT,
    email_official TEXT,
    website_verified TEXT,
    vision_mission TEXT,
    faculty_count INTEGER,
    faculty_list TEXT,
    org_structure TEXT,
    confidence REAL DEFAULT 0.0,
    last_run_id INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(university_id)
);

CREATE TABLE IF NOT EXISTS osint_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER NOT NULL REFERENCES universities(id),
    name TEXT,
    title TEXT,
    department TEXT,
    phone TEXT,
    email TEXT,
    source TEXT,
    source_url TEXT,
    confidence REAL DEFAULT 0.0,
    priority INTEGER DEFAULT 0,
    verified INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(university_id, phone, name)
);

CREATE TABLE IF NOT EXISTS osint_social_media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER NOT NULL REFERENCES universities(id),
    platform TEXT NOT NULL,
    handle TEXT,
    url TEXT,
    followers INTEGER,
    verified INTEGER DEFAULT 0,
    confidence REAL DEFAULT 0.0,
    source TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(university_id, platform, handle)
);

CREATE TABLE IF NOT EXISTS osint_news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER NOT NULL REFERENCES universities(id),
    title TEXT NOT NULL,
    summary TEXT,
    url TEXT,
    source TEXT,
    published_date TEXT,
    category TEXT,
    relevance_score REAL DEFAULT 0.0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS osint_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER NOT NULL REFERENCES universities(id),
    status TEXT DEFAULT 'running',
    trigger_type TEXT DEFAULT 'manual',
    agents_completed TEXT,
    agents_failed TEXT,
    contacts_found INTEGER DEFAULT 0,
    social_media_found INTEGER DEFAULT 0,
    news_found INTEGER DEFAULT 0,
    duration_seconds REAL,
    error TEXT,
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT
);
"""

_INDEXES_OSINT = """
CREATE INDEX IF NOT EXISTS idx_osint_profiles_university ON osint_profiles(university_id);
CREATE INDEX IF NOT EXISTS idx_osint_contacts_university ON osint_contacts(university_id);
CREATE INDEX IF NOT EXISTS idx_osint_social_university ON osint_social_media(university_id);
CREATE INDEX IF NOT EXISTS idx_osint_news_university ON osint_news(university_id);
CREATE INDEX IF NOT EXISTS idx_osint_runs_university ON osint_runs(university_id);
CREATE INDEX IF NOT EXISTS idx_osint_runs_status ON osint_runs(status);
"""

# ---------------------------------------------------------------------------
# CRM / PIC Profiling Tables
# ---------------------------------------------------------------------------

_DDL_CRM = """
CREATE TABLE IF NOT EXISTS crm_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER REFERENCES universities(id),
    university_name TEXT,
    requested_by TEXT,
    status TEXT DEFAULT 'pending',
    pic_name TEXT NOT NULL,
    pic_title TEXT,
    priority TEXT DEFAULT 'normal',
    notes TEXT,
    run_id INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS crm_pic_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL REFERENCES crm_requests(id),
    university_id INTEGER REFERENCES universities(id),
    full_name TEXT,
    full_name_source TEXT,
    title TEXT,
    title_source TEXT,
    teaching_subjects TEXT,
    teaching_subjects_source TEXT,
    tenure_years INTEGER,
    tenure_years_source TEXT,
    birth_date TEXT,
    birth_date_source TEXT,
    age INTEGER,
    origin_region TEXT,
    origin_region_source TEXT,
    education_history TEXT,
    education_history_source TEXT,
    photo_url TEXT,
    marital_status TEXT,
    marital_status_source TEXT,
    spouse_name TEXT,
    spouse_name_source TEXT,
    children_count INTEGER,
    children_count_source TEXT,
    family_residence TEXT,
    family_residence_source TEXT,
    campus_problems TEXT,
    campus_problems_source TEXT,
    campus_concerns TEXT,
    campus_concerns_source TEXT,
    campus_hopes TEXT,
    campus_hopes_source TEXT,
    hobbies TEXT,
    hobbies_source TEXT,
    favorite_food TEXT,
    favorite_food_source TEXT,
    outside_activities TEXT,
    outside_activities_source TEXT,
    personality_summary TEXT,
    recent_topics TEXT,
    communication_style TEXT,
    social_behavior_insights TEXT,
    linkedin_url TEXT,
    instagram_handle TEXT,
    facebook_url TEXT,
    twitter_handle TEXT,
    other_social TEXT,
    home_address TEXT,
    home_address_source TEXT,
    phone TEXT,
    email TEXT,
    overall_confidence REAL DEFAULT 0.0,
    fields_found INTEGER DEFAULT 0,
    fields_total INTEGER DEFAULT 0,
    fields_manual INTEGER DEFAULT 0,
    last_updated TEXT DEFAULT (datetime('now')),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS crm_profile_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL REFERENCES crm_requests(id),
    status TEXT DEFAULT 'running',
    agents_completed TEXT,
    agents_failed TEXT,
    duration_seconds REAL,
    error TEXT,
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS crm_profile_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES crm_pic_profiles(id),
    field_name TEXT NOT NULL,
    value TEXT,
    source_type TEXT,
    source_url TEXT,
    confidence REAL DEFAULT 0.0,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
"""

_INDEXES_CRM = """
CREATE INDEX IF NOT EXISTS idx_crm_requests_status ON crm_requests(status);
CREATE INDEX IF NOT EXISTS idx_crm_requests_university ON crm_requests(university_id);
CREATE INDEX IF NOT EXISTS idx_crm_pic_profiles_request ON crm_pic_profiles(request_id);
CREATE INDEX IF NOT EXISTS idx_crm_pic_profiles_university ON crm_pic_profiles(university_id);
CREATE INDEX IF NOT EXISTS idx_crm_profile_runs_request ON crm_profile_runs(request_id);
CREATE INDEX IF NOT EXISTS idx_crm_profile_sources_profile ON crm_profile_sources(profile_id);
"""

# ---------------------------------------------------------------------------
# University Groups
# ---------------------------------------------------------------------------

_DDL_UNIVERSITY_GROUPS = """
CREATE TABLE IF NOT EXISTS university_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS university_group_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES university_groups(id) ON DELETE CASCADE,
    university_id INTEGER NOT NULL REFERENCES universities(id) ON DELETE CASCADE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(group_id, university_id)
);
"""

_INDEXES_UNIVERSITY_GROUPS = """
CREATE INDEX IF NOT EXISTS idx_group_members_group ON university_group_members(group_id);
CREATE INDEX IF NOT EXISTS idx_group_members_univ ON university_group_members(university_id);
"""

_DDL_MARKETING = """
CREATE TABLE IF NOT EXISTS marketing_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    client_type TEXT NOT NULL,
    source TEXT DEFAULT 'manual',
    status TEXT DEFAULT 'draft',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS marketing_clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES marketing_groups(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    extra_data TEXT,
    search_status TEXT DEFAULT 'pending',
    error_message TEXT,
    ig_handle TEXT,
    ig_profile_url TEXT,
    ig_last_scraped_at DATETIME,
    ig_post_scrape_status TEXT,
    ig_post_scrape_error TEXT,
    ig_post_scrape_last_attempt_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS marketing_contact_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES marketing_clients(id) ON DELETE CASCADE,
    contact_type TEXT NOT NULL,
    value TEXT NOT NULL,
    source_url TEXT,
    source_type TEXT,
    confidence REAL DEFAULT 0.0,
    is_approved INTEGER DEFAULT 0,
    is_selected INTEGER DEFAULT 0,
    edited_value TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS marketing_contact_handoffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES marketing_groups(id) ON DELETE CASCADE,
    result_id INTEGER NOT NULL REFERENCES marketing_contact_results(id) ON DELETE CASCADE,
    handoff_type TEXT NOT NULL,
    campaign_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS marketing_ig_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES marketing_clients(id) ON DELETE CASCADE,
    ig_handle TEXT,
    post_url TEXT NOT NULL,
    image_url TEXT,
    caption TEXT,
    post_timestamp TEXT,
    source TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(client_id, post_url)
);

CREATE TABLE IF NOT EXISTS marketing_ig_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES marketing_clients(id) ON DELETE CASCADE,
    handle TEXT NOT NULL,
    profile_url TEXT,
    source TEXT,
    title TEXT,
    snippet TEXT,
    full_name TEXT,
    bio TEXT,
    external_url TEXT,
    external_domain TEXT,
    is_verified INTEGER DEFAULT 0,
    base_score REAL DEFAULT 0.0,
    affinity_score REAL DEFAULT 0.0,
    profile_score REAL DEFAULT 0.0,
    final_score REAL DEFAULT 0.0,
    llm_is_correct INTEGER,
    llm_confidence REAL DEFAULT 0.0,
    llm_reason TEXT,
    rank_order INTEGER,
    is_primary INTEGER DEFAULT 0,
    is_selected INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(client_id, handle)
);
"""

_INDEXES_MARKETING = """
CREATE INDEX IF NOT EXISTS idx_mc_group ON marketing_clients(group_id);
CREATE INDEX IF NOT EXISTS idx_mc_status ON marketing_clients(search_status);
CREATE INDEX IF NOT EXISTS idx_mcr_client ON marketing_contact_results(client_id);
CREATE INDEX IF NOT EXISTS idx_mcr_type ON marketing_contact_results(contact_type);
CREATE INDEX IF NOT EXISTS idx_mch_group ON marketing_contact_handoffs(group_id);
CREATE INDEX IF NOT EXISTS idx_mch_result ON marketing_contact_handoffs(result_id);
CREATE INDEX IF NOT EXISTS idx_mip_client ON marketing_ig_posts(client_id);
CREATE INDEX IF NOT EXISTS idx_mip_handle ON marketing_ig_posts(ig_handle);
CREATE INDEX IF NOT EXISTS idx_mic_client ON marketing_ig_candidates(client_id);
CREATE INDEX IF NOT EXISTS idx_mic_selected ON marketing_ig_candidates(client_id, is_selected, rank_order);
"""

# ---------------------------------------------------------------------------
# Initialization & connection helper
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """Create all tables if they do not already exist."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Enable WAL mode for concurrent read/write from multiple threads
        await db.execute("PRAGMA journal_mode=WAL")
        await db.executescript(_DDL)
        await db.executescript(_DDL_AGENT)
        await db.executescript(_DDL_CONFIG)
        await db.executescript(_DDL_AUTH)
        await db.executescript(_INDEXES)
        await db.executescript(_INDEXES_AGENT)
        await db.executescript(_INDEXES_AUTH)
        await db.executescript(_DDL_AUDIENSI)
        await db.executescript(_INDEXES_AUDIENSI)
        await db.executescript(_DDL_KNOWLEDGE)
        await db.executescript(_INDEXES_KNOWLEDGE)
        await db.executescript(_DDL_API_LOGS)
        await db.executescript(_INDEXES_API_LOGS)
        await db.executescript(_DDL_PIPELINE_LOGS)
        await db.executescript(_INDEXES_PIPELINE_LOGS)
        await db.executescript(_DDL_RELATED_IGS)
        await db.executescript(_INDEXES_RELATED_IGS)
        await db.executescript(_DDL_IG_ACCOUNTS)
        await db.executescript(_DDL_BLAST)
        await db.executescript(_DDL_EMAIL_BLAST)
        await db.executescript(_DDL_OSINT)
        await db.executescript(_INDEXES_OSINT)
        await db.executescript(_DDL_CRM)
        await db.executescript(_INDEXES_CRM)
        await db.executescript(_DDL_UNIVERSITY_GROUPS)
        await db.executescript(_INDEXES_UNIVERSITY_GROUPS)
        await db.executescript(_DDL_MARKETING)
        await db.executescript(_INDEXES_MARKETING)

        # Migration: add error_message column to marketing_clients if missing
        cursor = await db.execute("PRAGMA table_info(marketing_clients)")
        columns = {row[1] for row in await cursor.fetchall()}
        if "error_message" not in columns:
            await db.execute(
                "ALTER TABLE marketing_clients ADD COLUMN error_message TEXT"
            )
        if "ig_handle" not in columns:
            await db.execute(
                "ALTER TABLE marketing_clients ADD COLUMN ig_handle TEXT"
            )
        if "ig_profile_url" not in columns:
            await db.execute(
                "ALTER TABLE marketing_clients ADD COLUMN ig_profile_url TEXT"
            )
        if "ig_last_scraped_at" not in columns:
            await db.execute(
                "ALTER TABLE marketing_clients ADD COLUMN ig_last_scraped_at DATETIME"
            )
        if "ig_post_scrape_status" not in columns:
            await db.execute(
                "ALTER TABLE marketing_clients ADD COLUMN ig_post_scrape_status TEXT"
            )
        if "ig_post_scrape_error" not in columns:
            await db.execute(
                "ALTER TABLE marketing_clients ADD COLUMN ig_post_scrape_error TEXT"
            )
        if "ig_post_scrape_last_attempt_at" not in columns:
            await db.execute(
                "ALTER TABLE marketing_clients ADD COLUMN ig_post_scrape_last_attempt_at DATETIME"
            )

        cursor = await db.execute("PRAGMA table_info(marketing_ig_candidates)")
        candidate_columns = {row[1] for row in await cursor.fetchall()}
        if "affinity_score" not in candidate_columns:
            await db.execute(
                "ALTER TABLE marketing_ig_candidates ADD COLUMN affinity_score REAL DEFAULT 0.0"
            )

        async def _rebuild_email_cache_table_if_needed(table_name: str, recreate_script: str) -> None:
            cursor = await db.execute(f"PRAGMA table_info({table_name})")
            columns = {row[1] for row in await cursor.fetchall()}
            required_columns = {"cache_key", "mailbox_email", "uid", "sort_ts"}

            if required_columns.issubset(columns):
                return

            await db.execute(f"DROP TABLE IF EXISTS {table_name}")
            await db.executescript(recreate_script)
            await db.commit()

        await _rebuild_email_cache_table_if_needed(
            "email_inbox_cache",
            """
            CREATE TABLE IF NOT EXISTS email_inbox_cache (
                cache_key TEXT PRIMARY KEY,
                mailbox_email TEXT NOT NULL,
                uid INTEGER NOT NULL,
                sort_ts INTEGER NOT NULL DEFAULT 0,
                message_id TEXT,
                in_reply_to TEXT,
                from_email TEXT,
                from_name TEXT,
                to_email TEXT,
                subject TEXT,
                body TEXT,
                date TEXT,
                is_read INTEGER DEFAULT 0,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_inbox_cache_fetched ON email_inbox_cache(fetched_at DESC);
            CREATE INDEX IF NOT EXISTS idx_inbox_cache_sort ON email_inbox_cache(sort_ts DESC, uid DESC);
            CREATE INDEX IF NOT EXISTS idx_inbox_cache_mailbox_uid ON email_inbox_cache(mailbox_email, uid DESC);
            """,
        )

        await _rebuild_email_cache_table_if_needed(
            "email_sent_cache",
            """
            CREATE TABLE IF NOT EXISTS email_sent_cache (
                cache_key TEXT PRIMARY KEY,
                mailbox_email TEXT NOT NULL,
                uid INTEGER NOT NULL,
                sort_ts INTEGER NOT NULL DEFAULT 0,
                message_id TEXT,
                from_email TEXT,
                from_name TEXT,
                to_email TEXT,
                subject TEXT,
                body TEXT,
                date TEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_sent_cache_fetched ON email_sent_cache(fetched_at DESC);
            CREATE INDEX IF NOT EXISTS idx_sent_cache_sort ON email_sent_cache(sort_ts DESC, uid DESC);
            CREATE INDEX IF NOT EXISTS idx_sent_cache_mailbox_uid ON email_sent_cache(mailbox_email, uid DESC);
            """,
        )

        await db.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_inbox_cache_sort ON email_inbox_cache(sort_ts DESC, uid DESC);
            CREATE INDEX IF NOT EXISTS idx_inbox_cache_mailbox_uid ON email_inbox_cache(mailbox_email, uid DESC);
            CREATE INDEX IF NOT EXISTS idx_sent_cache_sort ON email_sent_cache(sort_ts DESC, uid DESC);
            CREATE INDEX IF NOT EXISTS idx_sent_cache_mailbox_uid ON email_sent_cache(mailbox_email, uid DESC);
            """
        )
        await db.commit()

        # Migration: add agent_reasoning column to conversations (idempotent)
        try:
            await db.execute(
                "ALTER TABLE conversations ADD COLUMN agent_reasoning TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add is_test column to conversations (idempotent)
        try:
            await db.execute(
                "ALTER TABLE conversations ADD COLUMN is_test BOOLEAN DEFAULT 0"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add followup_count column to conversations (idempotent)
        try:
            await db.execute(
                "ALTER TABLE conversations ADD COLUMN followup_count INTEGER DEFAULT 0"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add contact_name column to ig_contacts (idempotent)
        try:
            await db.execute(
                "ALTER TABLE ig_contacts ADD COLUMN contact_name TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add has_person_name flag to ig_contacts
        try:
            await db.execute(
                "ALTER TABLE ig_contacts ADD COLUMN has_person_name BOOLEAN DEFAULT 1"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add manual_contacted flag to ig_contacts
        try:
            await db.execute(
                "ALTER TABLE ig_contacts ADD COLUMN manual_contacted BOOLEAN DEFAULT 0"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add last_ig_scraped_at to universities for re-scrape cooldown
        try:
            await db.execute(
                "ALTER TABLE universities ADD COLUMN last_ig_scraped_at TIMESTAMP"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add rector_name to universities for audiensi
        try:
            await db.execute(
                "ALTER TABLE universities ADD COLUMN rector_name TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add source column to conversation_analyses for audiensi learning
        try:
            await db.execute(
                "ALTER TABLE conversation_analyses ADD COLUMN source TEXT DEFAULT 'outreach'"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add extracted_contact_name to conversations
        try:
            await db.execute(
                "ALTER TABLE conversations ADD COLUMN extracted_contact_name TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add extracted_contact_role to conversations
        try:
            await db.execute(
                "ALTER TABLE conversations ADD COLUMN extracted_contact_role TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add situation_tags column to knowledge_items
        try:
            await db.execute(
                "ALTER TABLE knowledge_items ADD COLUMN situation_tags TEXT DEFAULT ''"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add trigger_keywords column to knowledge_items
        try:
            await db.execute(
                "ALTER TABLE knowledge_items ADD COLUMN trigger_keywords TEXT DEFAULT ''"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add cached_tokens column to api_call_logs
        try:
            await db.execute(
                "ALTER TABLE api_call_logs ADD COLUMN cached_tokens INTEGER DEFAULT 0"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add last_response_id to conversations (Responses API session chaining)
        try:
            await db.execute(
                "ALTER TABLE conversations ADD COLUMN last_response_id TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add last_response_id to audiensi_conversations (Responses API session chaining)
        try:
            await db.execute(
                "ALTER TABLE audiensi_conversations ADD COLUMN last_response_id TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add enabled flag to universities (default enabled)
        try:
            await db.execute(
                "ALTER TABLE universities ADD COLUMN enabled BOOLEAN DEFAULT 1"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Index for enabled column
        await db.executescript(
            "CREATE INDEX IF NOT EXISTS idx_universities_enabled ON universities(enabled);"
        )
        # Migration: add bem_ig_handle to universities for BEM discovery
        try:
            await db.execute(
                "ALTER TABLE universities ADD COLUMN bem_ig_handle TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add bem_discovery_status to universities
        try:
            await db.execute(
                "ALTER TABLE universities ADD COLUMN bem_discovery_status TEXT DEFAULT 'pending'"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add updated_at to universities (older DBs may lack it)
        # Note: SQLite ALTER TABLE doesn't allow DEFAULT CURRENT_TIMESTAMP, so we add without default then backfill
        # Migration: add email_kampus to universities (from OSINT web profiler)
        try:
            await db.execute(
                "ALTER TABLE universities ADD COLUMN email_kampus TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists

        # Migration: add email_source to track source of email
        try:
            await db.execute(
                "ALTER TABLE universities ADD COLUMN email_source TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists

        # Migration: add student_count (from OSINT PDDIKTI)
        try:
            await db.execute(
                "ALTER TABLE universities ADD COLUMN student_count INTEGER"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists

        try:
            await db.execute(
                "ALTER TABLE universities ADD COLUMN updated_at TIMESTAMP"
            )
            await db.execute(
                "UPDATE universities SET updated_at = created_at WHERE updated_at IS NULL"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists

        # Migration: add bem_discovery_attempts to track retry count
        try:
            await db.execute(
                "ALTER TABLE universities ADD COLUMN bem_discovery_attempts INTEGER DEFAULT 0"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists

        # Migration: add source_ig_handle and source_ig_type to ig_posts (older DBs may lack them)
        try:
            await db.execute("ALTER TABLE ig_posts ADD COLUMN source_ig_handle TEXT")
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute("ALTER TABLE ig_posts ADD COLUMN source_ig_type TEXT")
            await db.commit()
        except Exception:
            pass  # Column already exists

        # Migration: add login_status column to ig_accounts
        try:
            await db.execute(
                "ALTER TABLE ig_accounts ADD COLUMN login_status TEXT DEFAULT 'untested'"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Migration: add last_login_test column to ig_accounts
        try:
            await db.execute(
                "ALTER TABLE ig_accounts ADD COLUMN last_login_test TIMESTAMP"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists

        # Migration: add letter_number to email_blast_recipients (for retry — reuse same letter number)
        try:
            await db.execute(
                "ALTER TABLE email_blast_recipients ADD COLUMN letter_number TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists

        # Migration: add invalid_count to email_blast_campaigns (for skipped invalid emails)
        try:
            await db.execute(
                "ALTER TABLE email_blast_campaigns ADD COLUMN invalid_count INTEGER DEFAULT 0"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists

        # Migration: add ownership metadata to email blast campaigns
        try:
            await db.execute(
                "ALTER TABLE email_blast_campaigns ADD COLUMN created_by_dms_user_id INTEGER"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists

        # Migration: enrich outbox rows with sender attribution and recipient linkage
        try:
            await db.execute(
                "ALTER TABLE email_outbox ADD COLUMN recipient_id INTEGER"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE email_outbox ADD COLUMN from_email TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE email_outbox ADD COLUMN from_name TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists

        await db.execute(
            """UPDATE email_outbox
               SET from_email = COALESCE(
                   from_email,
                   (SELECT c.from_email FROM email_blast_campaigns c WHERE c.id = email_outbox.campaign_id),
                   'sekretariat@asosiasi.ai'
               )
               WHERE from_email IS NULL OR trim(from_email) = ''"""
        )
        await db.execute(
            """UPDATE email_outbox
               SET from_name = COALESCE(
                   from_name,
                   (SELECT c.from_name FROM email_blast_campaigns c WHERE c.id = email_outbox.campaign_id),
                   'Sekretariat Asosiasi AI'
               )
               WHERE from_name IS NULL OR trim(from_name) = ''"""
        )
        await db.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_outbox_recipient ON email_outbox(recipient_id);
            CREATE INDEX IF NOT EXISTS idx_outbox_from_email ON email_outbox(from_email);
            """
        )
        await db.commit()
        try:
            await db.execute(
                "ALTER TABLE email_blast_campaigns ADD COLUMN created_by_email TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE email_blast_campaigns ADD COLUMN created_by_name TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE email_blast_campaigns ADD COLUMN started_by_dms_user_id INTEGER"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE email_blast_campaigns ADD COLUMN started_by_email TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE email_blast_campaigns ADD COLUMN started_by_name TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists

        # Migration: add embedding column to knowledge_items for semantic search
        try:
            await db.execute("ALTER TABLE knowledge_items ADD COLUMN embedding BLOB")
            await db.commit()
        except Exception:
            pass  # Column already exists

        # Migration: add embedding column to lessons for semantic search
        try:
            await db.execute("ALTER TABLE lessons ADD COLUMN embedding BLOB")
            await db.commit()
        except Exception:
            pass  # Column already exists

        # Migration: add advanced blast safety columns
        try:
            await db.execute(
                "ALTER TABLE blast_campaigns ADD COLUMN content_variation_enabled INTEGER DEFAULT 1"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE blast_campaigns ADD COLUMN schedule_enabled INTEGER DEFAULT 1"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE blast_campaigns ADD COLUMN schedule_timezone TEXT DEFAULT 'Asia/Jakarta'"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE blast_campaigns ADD COLUMN active_hours_start INTEGER DEFAULT 8"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE blast_campaigns ADD COLUMN active_hours_end INTEGER DEFAULT 21"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE blast_campaigns ADD COLUMN peak_hours_start INTEGER DEFAULT 10"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE blast_campaigns ADD COLUMN peak_hours_end INTEGER DEFAULT 14"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE blast_campaigns ADD COLUMN lunch_break_start INTEGER DEFAULT 12"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE blast_campaigns ADD COLUMN lunch_break_end INTEGER DEFAULT 13"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE blast_campaigns ADD COLUMN weekend_factor REAL DEFAULT 0.5"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE blast_campaigns ADD COLUMN auto_resume_enabled INTEGER DEFAULT 1"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE blast_campaigns ADD COLUMN auto_resume_at TIMESTAMP"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE blast_campaigns ADD COLUMN paused_reason TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists

        # Migration: add ownership metadata to blast campaigns
        try:
            await db.execute(
                "ALTER TABLE blast_campaigns ADD COLUMN created_by_dms_user_id INTEGER"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE blast_campaigns ADD COLUMN created_by_email TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE blast_campaigns ADD COLUMN created_by_name TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE blast_campaigns ADD COLUMN started_by_dms_user_id INTEGER"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE blast_campaigns ADD COLUMN started_by_email TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE blast_campaigns ADD COLUMN started_by_name TEXT"
            )
            await db.commit()
        except Exception:
            pass  # Column already exists

        await db.executescript(_INDEXES_BLAST)
        await db.executescript(_INDEXES_EMAIL_BLAST)

        # Migration: create contact_memory table for persistent per-contact notes
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS contact_memory (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                phone           TEXT NOT NULL,
                memory_text     TEXT NOT NULL,
                memory_type     TEXT DEFAULT 'general',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_contact_memory_phone ON contact_memory(phone);
        """)
        await db.commit()

        # Cleanup: mark any orphaned 'running' pipeline_logs as failed (from previous crash/restart)
        await db.execute(
            "UPDATE pipeline_logs SET status='failed', summary='Stale: cleaned up after restart' WHERE status='running'"
        )
        await db.commit()
    log.info("Database initialised at %s", DATABASE_PATH)


@asynccontextmanager
async def get_db():
    """Async context manager that yields an aiosqlite connection with row_factory."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


# ---------------------------------------------------------------------------
# Phone number validation
# ---------------------------------------------------------------------------


def validate_phone(number: str) -> str | None:
    """
    Validate and normalise an Indonesian **mobile** phone number.

    Accepts: 08xx…, 628xx…, +628xx…  (mobile only, not landlines)
    Returns: E.164 string (+62…) or None if the number is invalid/not mobile.
    """
    if not number:
        return None

    cleaned = number.strip().replace(" ", "").replace("-", "").replace(".", "")

    try:
        parsed = phonenumbers.parse(cleaned, "ID")
        if not phonenumbers.is_valid_number(parsed):
            return None
        # Only accept mobile numbers (reject landlines, toll-free, etc.)
        num_type = phonenumbers.number_type(parsed)
        if num_type not in (
            phonenumbers.PhoneNumberType.MOBILE,
            phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE,
        ):
            return None
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass

    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
    return dict(row)


def _rows_to_dicts(rows) -> list[dict[str, Any]]:
    return [_row_to_dict(r) for r in rows]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# University CRUD
# ---------------------------------------------------------------------------


async def add_university(
    name: str,
    pddikti_id: str | None = None,
    province: str | None = None,
    website: str | None = None,
    student_count: int | None = None,
) -> int:
    """Insert a university row and return the new id."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO universities (name, pddikti_id, province, website, student_count)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(pddikti_id) DO UPDATE SET
                name = excluded.name,
                province = excluded.province,
                website = excluded.website,
                student_count = excluded.student_count
            """,
            (name, pddikti_id, province, website, student_count),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def get_universities_by_status(
    status: str,
    limit: int = 100,
    offset: int = 0,
    last_id: int = 0,
    *,
    enabled_only: bool = True
) -> list[dict]:
    """Return universities by status with optional rolling mechanism.

    Args:
        status: Status to filter by (e.g., 'pending', 'ig_found')
        limit: Maximum number of results
        offset: Offset for pagination (legacy, use last_id for rolling)
        last_id: Last processed university ID for rolling (gets IDs > last_id)
        enabled_only: Only return enabled universities

    If last_id > 0, uses rolling mechanism (WHERE id > last_id).
    Otherwise uses legacy offset mechanism.
    """
    enabled_clause = " AND (enabled = 1 OR enabled IS NULL)" if enabled_only else ""

    if last_id > 0:
        # Rolling mechanism: get universities with ID > last_id
        async with get_db() as db:
            cursor = await db.execute(
                f"SELECT * FROM universities WHERE status = ? AND id > ?{enabled_clause} ORDER BY id LIMIT ?",
                (status, last_id, limit),
            )
            rows = await cursor.fetchall()
            return _rows_to_dicts(rows)
    else:
        # Legacy offset mechanism
        async with get_db() as db:
            cursor = await db.execute(
                f"SELECT * FROM universities WHERE status = ?{enabled_clause} LIMIT ? OFFSET ?",
                (status, limit, offset),
            )
            rows = await cursor.fetchall()
            return _rows_to_dicts(rows)


async def get_universities_for_ig_scraping(
    limit: int = 100, last_id: int = 0, *, enabled_only: bool = True
) -> list[dict]:
    """Return universities ready for IG post scraping.
    
    Requires:
    - status = 'ig_found'
    - bem_discovery_status IS NOT NULL AND != 'pending'
      (meaning Agent 4 has finished processing it).
    
    If last_id > 0, uses rolling mechanism (WHERE id > last_id).
    """
    enabled_clause = " AND (enabled = 1 OR enabled IS NULL)" if enabled_only else ""

    if last_id > 0:
        query = f"SELECT * FROM universities WHERE status = 'ig_found' AND bem_discovery_status IS NOT NULL AND bem_discovery_status != 'pending' AND id > ?{enabled_clause} ORDER BY id LIMIT ?"
        params = (last_id, limit)
    else:
        query = f"SELECT * FROM universities WHERE status = 'ig_found' AND bem_discovery_status IS NOT NULL AND bem_discovery_status != 'pending'{enabled_clause} ORDER BY id LIMIT ?"
        params = (limit,)

    async with get_db() as db:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_universities_by_ids(uni_ids: list[int]) -> list[dict]:
    """Return universities matching the given IDs (regardless of status/enabled)."""
    if not uni_ids:
        return []
    placeholders = ",".join("?" for _ in uni_ids)
    async with get_db() as db:
        cursor = await db.execute(
            f"SELECT * FROM universities WHERE id IN ({placeholders})",
            tuple(uni_ids),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_unextracted_posts_for_universities(uni_ids: list[int], limit: int = 200) -> list[dict]:
    """Return unextracted ig_posts for specific universities."""
    if not uni_ids:
        return []
    placeholders = ",".join("?" for _ in uni_ids)
    async with get_db() as db:
        cursor = await db.execute(
            f"""
            SELECT p.*, u.name AS university_name
            FROM ig_posts p
            JOIN universities u ON u.id = p.university_id
            WHERE p.phone_extracted = 0
              AND p.university_id IN ({placeholders})
            ORDER BY p.created_at
            LIMIT ?
            """,
            (*uni_ids, limit),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def update_university_status(uni_id: int, status: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE universities SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, uni_id),
        )
        await db.commit()
    # Broadcast university updated event
    await ws_manager.broadcast_type("university_updated", uni_id=uni_id, status=status)


async def update_university_website(uni_id: int, website: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE universities SET website = ?, updated_at = datetime('now') WHERE id = ? AND (website IS NULL OR website = '')",
            (website, uni_id),
        )
        await db.commit()


async def update_ig_handle(uni_id: int, handle: str, verified: bool = False) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE universities SET ig_handle = ?, ig_verified = ?, updated_at = datetime('now') WHERE id = ?",
            (handle, int(verified), uni_id),
        )
        await db.commit()


async def reset_ig_handle(uni_id: int) -> bool:
    """Clear IG handle and reset status to 'pending' so the agent re-searches."""
    async with get_db() as db:
        cur = await db.execute("SELECT id FROM universities WHERE id = ?", (uni_id,))
        if not await cur.fetchone():
            return False
        await db.execute(
            "UPDATE universities SET ig_handle = NULL, ig_verified = 0, status = 'pending', "
            "updated_at = datetime('now') WHERE id = ?",
            (uni_id,),
        )
        await db.commit()
    await ws_manager.broadcast_type("university_updated", uni_id=uni_id, status="pending")
    return True


async def update_secretariat_phone(uni_id: int, phone: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE universities SET secretariat_phone = ?, updated_at = datetime('now') WHERE id = ?",
            (phone, uni_id),
        )
        await db.commit()
    # Broadcast got_number event
    await ws_manager.broadcast_type("got_number", uni_id=uni_id, phone=phone)


async def update_university_email(uni_id: int, email: str, source: str = "osint") -> None:
    """Update the campus email on the university record."""
    async with get_db() as db:
        await db.execute(
            "UPDATE universities SET email_kampus = ?, email_source = ?, updated_at = datetime('now') WHERE id = ?",
            (email, source, uni_id),
        )
        await db.commit()
    log.info("[DB] Updated email_kampus for university %d: %s (source: %s)", uni_id, email, source)


async def update_university_rector_name(uni_id: int, rector_name: str) -> None:
    """Set the rector name on the university record."""
    async with get_db() as db:
        await db.execute(
            "UPDATE universities SET rector_name = ?, updated_at = datetime('now') WHERE id = ?",
            (rector_name, uni_id),
        )
        await db.commit()


async def update_student_count(uni_id: int, student_count: int | None) -> None:
    """Set the student count on the university record."""
    async with get_db() as db:
        await db.execute(
            "UPDATE universities SET student_count = ?, updated_at = datetime('now') WHERE id = ?",
            (student_count, uni_id),
        )
        await db.commit()


async def update_bem_handle(uni_id: int, handle: str) -> None:
    """Set the BEM IG handle on the university record."""
    async with get_db() as db:
        await db.execute(
            "UPDATE universities SET bem_ig_handle = ?, updated_at = datetime('now') WHERE id = ?",
            (handle, uni_id),
        )
        await db.commit()


async def get_university_by_id(uni_id: int) -> dict | None:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM universities WHERE id = ?",
            (uni_id,),
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def search_universities(query: str) -> list[dict]:
    pattern = f"%{query}%"
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM universities WHERE name LIKE ? OR province LIKE ?",
            (pattern, pattern),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_all_universities(limit: int = 5000, offset: int = 0) -> list[dict]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM universities ORDER BY id LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def list_universities_paginated(
    *,
    search: str | None = None,
    status: str | None = None,
    province: str | None = None,
    has_ig: bool | None = None,
    enabled: bool | None = None,
    limit: int = 25,
    offset: int = 0,
    sort_by: str | None = None,
    order: str | None = None,
    group_id: int | None = None,
) -> dict:
    """Return {data: [...], total: N} with combined filters and sorting."""
    conditions: list[str] = []
    params: list = []

    if search:
        conditions.append("(u.name LIKE ? OR u.province LIKE ? OR u.ig_handle LIKE ?)")
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern])
    if status:
        conditions.append("u.status = ?")
        params.append(status)
    if province:
        conditions.append("u.province = ?")
        params.append(province)
    if has_ig is True:
        conditions.append("u.ig_handle IS NOT NULL AND u.ig_handle != ''")
    elif has_ig is False:
        conditions.append("(u.ig_handle IS NULL OR u.ig_handle = '')")
    if enabled is True:
        conditions.append("(u.enabled = 1 OR u.enabled IS NULL)")
    elif enabled is False:
        conditions.append("u.enabled = 0")

    # Join with university_group_members if filtering by group
    join_clause = ""
    if group_id is not None:
        join_clause = "INNER JOIN university_group_members m ON m.university_id = u.id"
        conditions.append("m.group_id = ?")
        params.append(group_id)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # Build ORDER BY clause
    order_by = "COALESCE(u.updated_at, u.created_at) DESC"  # default
    if sort_by:
        # Validate sort_by to prevent SQL injection
        allowed_sorts = {
            'student_count': 'student_count',
            'name': 'name',
            'province': 'province',
            'created_at': 'created_at',
            'updated_at': 'updated_at',
        }
        sort_column = allowed_sorts.get(sort_by, 'updated_at')
        sort_order = 'DESC' if order and order.lower() == 'desc' else 'ASC'
        order_by = f"{sort_column} {sort_order}"

    async with get_db() as db:
        # Total count
        cursor = await db.execute(f"SELECT COUNT(*) FROM universities u {join_clause} {where}", params)
        row = await cursor.fetchone()
        total = row[0] if row else 0

        # Data page - include contact counts as derived columns via correlated subqueries
        cursor = await db.execute(
            f"""SELECT u.*,
                (SELECT COUNT(*) FROM ig_contacts c WHERE c.university_id = u.id) AS total_contacts,
                (SELECT COUNT(*) FROM ig_contacts c WHERE c.university_id = u.id
                    AND (c.manual_contacted = 1
                         OR EXISTS (
                             SELECT 1 FROM conversations cv
                             WHERE cv.contact_phone = c.phone_number
                               AND cv.university_id = c.university_id
                         ))
                ) AS contacted_contacts
            FROM universities u {join_clause} {where}
            ORDER BY {order_by} LIMIT ? OFFSET ?""",
            params + [limit, offset],
        )
        rows = await cursor.fetchall()
        return {"data": _rows_to_dicts(rows), "total": total}


async def get_university_provinces() -> list[str]:
    """Return distinct non-null province values, sorted."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT DISTINCT province FROM universities WHERE province IS NOT NULL AND province != '' ORDER BY province"
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


async def toggle_university_enabled(uni_id: int, enabled: bool) -> bool:
    """Set enabled flag for a single university. Returns True if row was found."""
    async with get_db() as db:
        cursor = await db.execute(
            "UPDATE universities SET enabled = ?, updated_at = datetime('now') WHERE id = ?",
            (int(enabled), uni_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def touch_university_updated(uni_id: int) -> None:
    """Update the updated_at timestamp for a university (call when any related data changes)."""
    async with get_db() as db:
        await db.execute(
            "UPDATE universities SET updated_at = datetime('now') WHERE id = ?",
            (uni_id,),
        )
        await db.commit()


async def bulk_toggle_universities_enabled(uni_ids: list[int], enabled: bool) -> int:
    """Set enabled flag for multiple universities. Returns number updated."""
    if not uni_ids:
        return 0
    placeholders = ",".join("?" for _ in uni_ids)
    async with get_db() as db:
        cursor = await db.execute(
            f"UPDATE universities SET enabled = ? WHERE id IN ({placeholders})",
            [int(enabled)] + uni_ids,
        )
        await db.commit()
        return cursor.rowcount


async def export_universities_filtered(
    *,
    search: str | None = None,
    status: str | None = None,
    province: str | None = None,
    has_ig: bool | None = None,
    enabled: bool | None = None,
) -> list[dict]:
    """Return all universities matching filters (no pagination) for export."""
    conditions: list[str] = []
    params: list = []

    if search:
        conditions.append("(name LIKE ? OR province LIKE ? OR ig_handle LIKE ?)")
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern])
    if status:
        conditions.append("status = ?")
        params.append(status)
    if province:
        conditions.append("province = ?")
        params.append(province)
    if has_ig is True:
        conditions.append("ig_handle IS NOT NULL AND ig_handle != ''")
    elif has_ig is False:
        conditions.append("(ig_handle IS NULL OR ig_handle = '')")
    if enabled is True:
        conditions.append("(enabled = 1 OR enabled IS NULL)")
    elif enabled is False:
        conditions.append("enabled = 0")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    async with get_db() as db:
        cursor = await db.execute(
            f"SELECT * FROM universities {where} ORDER BY id",
            params,
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def export_universities_by_ids(ids: list[int]) -> list[dict]:
    """Return universities matching specific IDs for export."""
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    async with get_db() as db:
        cursor = await db.execute(
            f"SELECT * FROM universities WHERE id IN ({placeholders}) ORDER BY id",
            ids,
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def export_contacts_filtered(
    *,
    search: str | None = None,
    status: str | None = None,
    province: str | None = None,
    has_ig: bool | None = None,
    enabled: bool | None = None,
    university_ids: list[int] | None = None,
) -> list[dict]:
    """Return contacts for export with filters.

    Returns a list of dict with: university_name, contact_name, phone_number
    """
    conditions: list[str] = []
    params: list = []

    if university_ids:
        placeholders = ",".join("?" for _ in university_ids)
        conditions.append(f"u.id IN ({placeholders})")
        params.extend(university_ids)
    else:
        # Apply filters only if not using specific IDs
        if search:
            conditions.append("(u.name LIKE ? OR u.province LIKE ? OR u.ig_handle LIKE ?)")
            pattern = f"%{search}%"
            params.extend([pattern, pattern, pattern])
        if status:
            conditions.append("u.status = ?")
            params.append(status)
        if province:
            conditions.append("u.province = ?")
            params.append(province)
        if has_ig is True:
            conditions.append("u.ig_handle IS NOT NULL AND u.ig_handle != ''")
        elif has_ig is False:
            conditions.append("(u.ig_handle IS NULL OR u.ig_handle = '')")
        if enabled is True:
            conditions.append("(u.enabled = 1 OR u.enabled IS NULL)")
        elif enabled is False:
            conditions.append("u.enabled = 0")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with get_db() as db:
        cursor = await db.execute(
            f"""
            SELECT
                u.name as university_name,
                c.contact_name,
                c.phone_number
            FROM ig_contacts c
            JOIN universities u ON u.id = c.university_id
            {where_clause}
            ORDER BY u.name, c.contact_name
            """,
            params,
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def match_university_names(names: list[str]) -> list[dict]:
    """Fuzzy-match a list of university name queries against the database.

    Uses LIKE matching: each query is searched as a substring (case-insensitive).
    Returns one match per query (best = exact match, then shortest name match).
    """
    results: list[dict] = []
    seen_ids: set[int] = set()

    async with get_db() as db:
        for query_name in names:
            query_name = query_name.strip()
            if not query_name:
                continue

            # Try exact match first (case-insensitive)
            cursor = await db.execute(
                "SELECT id, name, province, status, ig_handle FROM universities WHERE LOWER(name) = LOWER(?)",
                (query_name,),
            )
            row = await cursor.fetchone()

            if row:
                if row["id"] not in seen_ids:
                    seen_ids.add(row["id"])
                    results.append({
                        "id": row["id"],
                        "name": row["name"],
                        "province": row["province"],
                        "status": row["status"],
                        "ig_handle": row["ig_handle"],
                        "matched_query": query_name,
                        "match_type": "exact",
                    })
                continue

            # Fallback to LIKE (substring) match — pick shortest name (most specific)
            cursor = await db.execute(
                "SELECT id, name, province, status, ig_handle FROM universities WHERE LOWER(name) LIKE LOWER(?) ORDER BY LENGTH(name) ASC LIMIT 5",
                (f"%{query_name}%",),
            )
            like_rows = await cursor.fetchall()
            for r in like_rows:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    results.append({
                        "id": r["id"],
                        "name": r["name"],
                        "province": r["province"],
                        "status": r["status"],
                        "ig_handle": r["ig_handle"],
                        "matched_query": query_name,
                        "match_type": "partial",
                    })
                    break  # one match per query

    return results


# ---------------------------------------------------------------------------
# IG Contacts CRUD
# ---------------------------------------------------------------------------


async def add_ig_contact(
    university_id: int,
    phone_number: str,
    source_post_url: str | None = None,
    source_image_url: str | None = None,
    contact_name: str | None = None,
    has_person_name: bool = True,
) -> int | None:
    """Add a contact and update university's updated_at timestamp."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT OR IGNORE INTO ig_contacts
                (university_id, phone_number, contact_name, source_post_url, source_image_url, has_person_name)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (university_id, phone_number, contact_name, source_post_url, source_image_url, has_person_name),
        )
        await db.commit()
        # Touch university updated_at when a new contact is added
        if cursor.rowcount > 0:
            await touch_university_updated(university_id)
        return cursor.lastrowid if cursor.rowcount > 0 else None


async def get_contacts_for_university(university_id: int) -> list[dict]:
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT ic.*,
                   CASE
                       WHEN c.id IS NOT NULL THEN c.state
                       ELSE NULL
                   END AS conversation_state,
                   c.id AS conversation_id
            FROM ig_contacts ic
            LEFT JOIN conversations c
                   ON c.contact_phone = ic.phone_number
                  AND c.university_id = ic.university_id
            WHERE ic.university_id = ?
            ORDER BY ic.created_at
            """,
            (university_id,),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def toggle_contact_manual_status(contact_id: int, contacted: bool) -> dict | None:
    """Toggle the manual_contacted flag on an ig_contact."""
    async with get_db() as db:
        await db.execute(
            "UPDATE ig_contacts SET manual_contacted = ? WHERE id = ?",
            (1 if contacted else 0, contact_id),
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT * FROM ig_contacts WHERE id = ?", (contact_id,)
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def bulk_match_contacts_by_phone(phone_numbers: list[str]) -> dict:
    """
    Given a list of raw phone numbers (any format), normalise them and look up
    matching ig_contacts.  Returns {matched: [...], not_matched: [...]}.
    """
    # Normalise all inputs
    normalised_map: dict[str, str] = {}      # e164 -> original
    invalid_numbers: list[str] = []

    for raw in phone_numbers:
        raw = raw.strip()
        if not raw:
            continue
        e164 = validate_phone(raw)
        if e164:
            normalised_map[e164] = raw
        else:
            invalid_numbers.append(raw)

    if not normalised_map:
        return {"matched": [], "not_matched": invalid_numbers}

    async with get_db() as db:
        placeholders = ",".join("?" for _ in normalised_map)
        cursor = await db.execute(
            f"""
            SELECT ic.*, u.name AS university_name,
                   c.state AS conversation_state,
                   c.id    AS conversation_id
            FROM ig_contacts ic
            LEFT JOIN universities u ON u.id = ic.university_id
            LEFT JOIN conversations c
                   ON c.contact_phone = ic.phone_number
                  AND c.university_id = ic.university_id
            WHERE ic.phone_number IN ({placeholders})
            ORDER BY u.name, ic.phone_number
            """,
            list(normalised_map.keys()),
        )
        rows = await cursor.fetchall()
        matched = _rows_to_dicts(rows)

    # Find which normalised numbers actually matched
    matched_phones = {r["phone_number"] for r in matched}
    not_matched: list[str] = []
    for e164, original in normalised_map.items():
        if e164 not in matched_phones:
            not_matched.append(original)
    not_matched.extend(invalid_numbers)

    return {"matched": matched, "not_matched": not_matched}


async def bulk_update_contact_status(contact_ids: list[int], contacted: bool) -> int:
    """Bulk set manual_contacted flag for a list of contact IDs. Returns count updated."""
    if not contact_ids:
        return 0
    async with get_db() as db:
        placeholders = ",".join("?" for _ in contact_ids)
        cursor = await db.execute(
            f"UPDATE ig_contacts SET manual_contacted = ? WHERE id IN ({placeholders})",
            [1 if contacted else 0] + contact_ids,
        )
        await db.commit()
        return cursor.rowcount


async def get_unused_contacts() -> list[dict]:
    """Return IG contacts that have no matching conversation yet."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT ic.*
            FROM ig_contacts ic
            LEFT JOIN conversations c ON c.contact_phone = ic.phone_number
            WHERE c.id IS NULL
            ORDER BY ic.created_at
            """,
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# IG Posts CRUD
# ---------------------------------------------------------------------------


async def add_ig_post(
    university_id: int,
    post_url: str,
    image_url: str | None = None,
    caption: str | None = None,
    post_timestamp: str | None = None,
    source_ig_handle: str | None = None,
    source_ig_type: str | None = None,
) -> int | None:
    """Insert a scraped post row (INSERT OR IGNORE for dedup).

    Args:
        university_id: Parent university ID
        post_url: URL of the Instagram post
        image_url: URL of the post image
        caption: Post caption text
        post_timestamp: When the post was made
        source_ig_handle: Which IG account this came from (e.g., 'bem.umj', 'univ_official')
        source_ig_type: Type of IG account ('main' for official, or 'bem', 'humas', 'pmb', etc.)
    """
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT OR IGNORE INTO ig_posts
                (university_id, post_url, image_url, caption, post_timestamp, source_ig_handle, source_ig_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (university_id, post_url, image_url, caption, post_timestamp, source_ig_handle, source_ig_type),
        )
        await db.commit()
        # Touch university updated_at when a new post is added
        if cursor.rowcount > 0:
            await touch_university_updated(university_id)
        return cursor.lastrowid if cursor.rowcount > 0 else None


async def get_unextracted_posts(limit: int = 50) -> list[dict]:
    """Return ig_posts rows that haven't been processed for phone extraction (enabled universities only)."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT p.*, u.name AS university_name
            FROM ig_posts p
            JOIN universities u ON u.id = p.university_id
            WHERE p.phone_extracted = 0
              AND (u.enabled = 1 OR u.enabled IS NULL)
            ORDER BY p.created_at
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def mark_post_extracted(post_id: int, phones_found: int) -> None:
    """Mark a post as processed and record how many phones were found."""
    async with get_db() as db:
        await db.execute(
            "UPDATE ig_posts SET phone_extracted = 1, phones_found = ? WHERE id = ?",
            (phones_found, post_id),
        )
        await db.commit()


async def count_posts_for_university(university_id: int, only_unextracted: bool = False) -> int:
    """Return total post count (or unextracted count) for a university."""
    async with get_db() as db:
        where = "university_id = ?"
        if only_unextracted:
            where += " AND phone_extracted = 0"
        cursor = await db.execute(
            f"SELECT COUNT(*) FROM ig_posts WHERE {where}",
            (university_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_post_urls_for_university(university_id: int) -> set[str]:
    """Return set of all post_url values already stored for a university."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT post_url FROM ig_posts WHERE university_id = ?",
            (university_id,),
        )
        rows = await cursor.fetchall()
        return {row[0] for row in rows}


# ---------------------------------------------------------------------------
# University Related IGs CRUD (BEM discovery)
# ---------------------------------------------------------------------------


async def add_related_ig(
    university_id: int,
    ig_handle: str,
    relation_type: str = "bem",
    source: str = "following",
    confidence: float = 0.0,
) -> int | None:
    """Insert a related IG account for a university (INSERT OR IGNORE for dedup).

    Updates the university's updated_at timestamp when a new related IG is added.
    """
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT OR IGNORE INTO university_related_igs
                (university_id, ig_handle, relation_type, source, confidence)
            VALUES (?, ?, ?, ?, ?)
            """,
            (university_id, ig_handle, relation_type, source, confidence),
        )
        await db.commit()
        # Touch university updated_at when a new related IG is added
        if cursor.rowcount > 0:
            await touch_university_updated(university_id)
        return cursor.lastrowid if cursor.rowcount > 0 else None


async def get_related_igs_for_university(
    university_id: int, relation_type: str | None = None
) -> list[dict]:
    """Return all related IG accounts for a university."""
    async with get_db() as db:
        if relation_type:
            cursor = await db.execute(
                "SELECT * FROM university_related_igs WHERE university_id = ? AND relation_type = ?",
                (university_id, relation_type),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM university_related_igs WHERE university_id = ?",
                (university_id,),
            )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_unscraped_related_igs(limit: int = 50) -> list[dict]:
    """Return related IG accounts that haven't had their posts scraped yet (enabled universities only)."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT r.*, u.name AS university_name
            FROM university_related_igs r
            JOIN universities u ON u.id = r.university_id
            WHERE r.posts_scraped = 0
              AND (u.enabled = 1 OR u.enabled IS NULL)
            ORDER BY r.discovered_at
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def mark_related_ig_scraped(related_ig_id: int) -> None:
    """Mark a related IG account as having had its posts scraped."""
    async with get_db() as db:
        await db.execute(
            "UPDATE university_related_igs SET posts_scraped = 1 WHERE id = ?",
            (related_ig_id,),
        )
        await db.commit()


async def update_bem_handle(uni_id: int, handle: str) -> None:
    """Set the BEM IG handle on the university record."""
    async with get_db() as db:
        await db.execute(
            "UPDATE universities SET bem_ig_handle = ? WHERE id = ?",
            (handle, uni_id),
        )
        await db.commit()


async def update_bem_discovery_status(uni_id: int, status: str, increment_attempts: bool = False) -> None:
    """Update the BEM discovery status on the university record.

    When increment_attempts=True, also bumps the bem_discovery_attempts counter.
    """
    async with get_db() as db:
        if increment_attempts:
            await db.execute(
                """UPDATE universities
                   SET bem_discovery_status = ?,
                       bem_discovery_attempts = COALESCE(bem_discovery_attempts, 0) + 1
                   WHERE id = ?""",
                (status, uni_id),
            )
        else:
            await db.execute(
                "UPDATE universities SET bem_discovery_status = ? WHERE id = ?",
                (status, uni_id),
            )
        await db.commit()


async def get_bem_discovery_attempts(uni_id: int) -> int:
    """Return the current bem_discovery_attempts count for a university."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT COALESCE(bem_discovery_attempts, 0) FROM universities WHERE id = ?",
            (uni_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_universities_for_bem_discovery(
    limit: int = 50,
    last_id: int = 0,
) -> list[dict]:
    """Return universities that are ready for BEM discovery.

    Requires: ig_handle is set (ig_found or later), BEM not yet discovered,
    and university is enabled.

    Retryable statuses:
      - NULL / 'pending'     — never attempted
      - 'no_following'       — IG account had empty following (transient: rate limit / private)
      - 'not_found'          — following fetched but keyword/LLM found nothing (retry on next cycle)
      - 'error'              — Python exception during processing (retry up to _MAX_BEM_ATTEMPTS)
      - 'session_error'      — all IG sessions were down when this ran (infra failure, retry freely)

    Non-retryable:
      - 'discovered'         — already found related IGs, no need to re-run
      - 'no_ig_handle'       — no IG handle, Agent 1 must run first

    Uses rolling mechanism when last_id > 0.
    """
    _retryable = "('pending', 'no_following', 'not_found', 'error', 'session_error')"
    if last_id > 0:
        # Rolling mechanism
        async with get_db() as db:
            cursor = await db.execute(
                f"""
                SELECT * FROM universities
                WHERE ig_handle IS NOT NULL AND ig_handle != ''
                  AND (bem_discovery_status IS NULL OR bem_discovery_status IN {_retryable})
                  AND id > ?
                  AND (enabled = 1 OR enabled IS NULL)
                ORDER BY id
                LIMIT ?
                """,
                (last_id, limit),
            )
            rows = await cursor.fetchall()
            return _rows_to_dicts(rows)
    else:
        # Legacy order by created_at
        async with get_db() as db:
            cursor = await db.execute(
                f"""
                SELECT * FROM universities
                WHERE ig_handle IS NOT NULL AND ig_handle != ''
                  AND (bem_discovery_status IS NULL OR bem_discovery_status IN {_retryable})
                  AND (enabled = 1 OR enabled IS NULL)
                ORDER BY created_at
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return _rows_to_dicts(rows)


async def get_pipeline_status() -> dict:
    """Return a breakdown of pipeline stages for /pipeline/status."""
    async with get_db() as db:
        # University status counts
        cursor = await db.execute(
            "SELECT status, COUNT(*) AS count FROM universities GROUP BY status"
        )
        rows = await cursor.fetchall()
        status_counts = {r["status"]: r["count"] for r in rows}

        # Unprocessed posts
        cursor = await db.execute(
            "SELECT COUNT(*) AS total FROM ig_posts WHERE phone_extracted = 0"
        )
        row = await cursor.fetchone()
        posts_unprocessed = row["total"] if row else 0

        # Total contacts
        cursor = await db.execute("SELECT COUNT(*) AS total FROM ig_contacts")
        row = await cursor.fetchone()
        total_contacts = row["total"] if row else 0

        # Currently running agents
        cursor = await db.execute(
            """SELECT id, agent_type, trigger_type, started_at,
                      items_processed, items_success, summary
               FROM pipeline_logs
               WHERE status = 'running'
               ORDER BY started_at DESC"""
        )
        running_rows = await cursor.fetchall()
        running_agents = []
        for r in running_rows:
            entry: dict = {
                "id": r["id"],
                "agent_type": r["agent_type"],
                "trigger_type": r["trigger_type"],
                "started_at": r["started_at"],
                "items_processed": r["items_processed"] or 0,
                "items_success": r["items_success"] or 0,
            }
            # Parse summary to get targeted_university_ids count
            if r["summary"]:
                import json as _json
                try:
                    s = _json.loads(r["summary"]) if isinstance(r["summary"], str) else r["summary"]
                    if isinstance(s, dict) and "targeted_university_ids" in s:
                        entry["target_count"] = len(s["targeted_university_ids"])
                except Exception:
                    pass
            running_agents.append(entry)

    return {
        "pending": status_counts.get("pending", 0),
        "ig_found": status_counts.get("ig_found", 0),
        "ig_scraped": status_counts.get("ig_scraped", 0),
        "contacted": status_counts.get("contacted", 0),
        "got_number": status_counts.get("got_number", 0),
        "failed": status_counts.get("failed", 0),
        "posts_unprocessed": posts_unprocessed,
        "total_contacts": total_contacts,
        "running_agents": running_agents,
    }


# ---------------------------------------------------------------------------
# Conversations CRUD
# ---------------------------------------------------------------------------

_TERMINAL_STATES = ("GOT_NUMBER", "REFUSED", "ABANDONED")


async def create_conversation(
    university_id: int | None, contact_phone: str, is_test: bool = False
) -> int:
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO conversations (university_id, contact_phone, state, is_test, created_at)
            VALUES (?, ?, 'PENDING', ?, ?)
            """,
            (university_id, contact_phone, int(is_test), _utcnow()),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def update_conversation_state(conv_id: int, state: str, **kwargs) -> None:
    """
    Update the state of a conversation plus any extra fields supplied as
    keyword arguments (message_history, extracted_number, last_message_at,
    next_action_at, attempt_count).
    """
    allowed_fields = {
        "message_history",
        "extracted_number",
        "extracted_contact_name",
        "extracted_contact_role",
        "last_message_at",
        "next_action_at",
        "attempt_count",
        "followup_count",
        "agent_reasoning",
    }
    extra = {k: v for k, v in kwargs.items() if k in allowed_fields}

    set_clauses = ["state = ?"]
    values: list[Any] = [state]

    for field, value in extra.items():
        set_clauses.append(f"{field} = ?")
        values.append(value)

    values.append(conv_id)
    sql = f"UPDATE conversations SET {', '.join(set_clauses)} WHERE id = ?"

    async with get_db() as db:
        await db.execute(sql, values)
        await db.commit()


async def get_active_conversations(include_test: bool = True) -> list[dict]:
    """Return conversations not yet in a terminal state."""
    placeholders = ",".join("?" * len(_TERMINAL_STATES))
    test_clause = "" if include_test else " AND is_test = 0"
    async with get_db() as db:
        cursor = await db.execute(
            f"SELECT * FROM conversations WHERE state NOT IN ({placeholders}){test_clause}",
            _TERMINAL_STATES,
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_conversations_needing_followup(hours_threshold: int) -> list[dict]:
    """
    Return conversations in WAITING_REPLY or FOLLOWUP_SENT state whose
    last_message_at is older than *hours_threshold* hours.
    """
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT * FROM conversations
            WHERE state IN ('WAITING_REPLY', 'FOLLOWUP_SENT')
              AND last_message_at IS NOT NULL
              AND is_test = 0
              AND (
                (julianday('now') - julianday(last_message_at)) * 24 >= ?
              )
            ORDER BY last_message_at
            """,
            (hours_threshold,),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_conversation_by_phone(phone: str) -> dict | None:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM conversations WHERE contact_phone = ? ORDER BY created_at DESC LIMIT 1",
            (phone,),
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def get_posts_for_university(university_id: int) -> list[dict]:
    """Return all ig_posts for a given university."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM ig_posts WHERE university_id = ? ORDER BY created_at DESC",
            (university_id,),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_post_count_for_university(university_id: int) -> int:
    """Return the total number of posts for a given university."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) as count FROM ig_posts WHERE university_id = ?",
            (university_id,),
        )
        row = await cursor.fetchone()
        return row["count"] if row else 0


async def get_conversations_filtered(
    state: str | None = None,
    university_id: int | None = None,
    is_test: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Return conversations with optional filters and pagination."""
    conditions = []
    params: list = []

    if state:
        conditions.append("c.state = ?")
        params.append(state)
    if university_id:
        conditions.append("c.university_id = ?")
        params.append(university_id)
    if is_test is not None:
        conditions.append("c.is_test = ?")
        params.append(int(is_test))

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with get_db() as db:
        cursor = await db.execute(
            f"""
            SELECT c.*, u.name AS university_name
            FROM conversations c
            LEFT JOIN universities u ON u.id = c.university_id
            {where}
            ORDER BY c.last_message_at DESC NULLS LAST
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_conversation_by_id(conv_id: int) -> dict | None:
    """Return a single conversation by ID with university name."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT c.*, u.name AS university_name
            FROM conversations c
            LEFT JOIN universities u ON u.id = c.university_id
            WHERE c.id = ?
            """,
            (conv_id,),
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def add_message_to_history(conv_id: int, role: str, content: str) -> None:
    """Append a {role, content, timestamp} entry to the JSON message_history column."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT message_history FROM conversations WHERE id = ?",
            (conv_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            log.warning("add_message_to_history: conversation %d not found", conv_id)
            return

        history: list[dict] = json.loads(row["message_history"] or "[]")
        history.append({"role": role, "content": content, "timestamp": _utcnow()})

        await db.execute(
            "UPDATE conversations SET message_history = ?, last_message_at = ? WHERE id = ?",
            (json.dumps(history), _utcnow(), conv_id),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Daily Quota
# ---------------------------------------------------------------------------


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def get_today_quota() -> dict:
    today = _today()
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT messages_sent, conversations_started FROM daily_quota WHERE date = ?",
            (today,),
        )
        row = await cursor.fetchone()
        if row:
            return _row_to_dict(row)
        return {"messages_sent": 0, "conversations_started": 0}


async def increment_quota(field: str) -> None:
    """Increment *field* (messages_sent or conversations_started) for today."""
    if field not in ("messages_sent", "conversations_started"):
        raise ValueError(f"Unknown quota field: {field}")

    today = _today()
    async with get_db() as db:
        await db.execute(
            f"""
            INSERT INTO daily_quota (date, {field}) VALUES (?, 1)
            ON CONFLICT(date) DO UPDATE SET {field} = {field} + 1
            """,
            (today,),
        )
        await db.commit()


async def can_send_today() -> bool:
    """Return True if conversations_started is below MAX_DAILY_CONVERSATIONS."""
    quota = await get_today_quota()
    return quota["conversations_started"] < cfg.MAX_DAILY_CONVERSATIONS


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------


async def get_dashboard_stats() -> dict:
    """Return aggregate counts for the dashboard."""
    async with get_db() as db:
        # Status breakdown for universities
        cursor = await db.execute(
            "SELECT status, COUNT(*) AS count FROM universities GROUP BY status"
        )
        rows = await cursor.fetchall()
        status_counts = {r["status"]: r["count"] for r in rows}

        # Total universities
        cursor = await db.execute("SELECT COUNT(*) AS total FROM universities")
        row = await cursor.fetchone()
        total_universities = row["total"] if row else 0

        # Universities with IG handle
        cursor = await db.execute(
            "SELECT COUNT(*) AS total FROM universities WHERE ig_handle IS NOT NULL AND ig_handle != ''"
        )
        row = await cursor.fetchone()
        universities_with_ig = row["total"] if row else 0

        # Universities with secretariat phone
        cursor = await db.execute(
            "SELECT COUNT(*) AS total FROM universities WHERE secretariat_phone IS NOT NULL AND secretariat_phone != ''"
        )
        row = await cursor.fetchone()
        universities_with_phone = row["total"] if row else 0

        # Total IG contacts
        cursor = await db.execute("SELECT COUNT(*) AS total FROM ig_contacts")
        row = await cursor.fetchone()
        total_contacts = row["total"] if row else 0

        # Total conversations
        cursor = await db.execute("SELECT COUNT(*) AS total FROM conversations")
        row = await cursor.fetchone()
        total_conversations = row["total"] if row else 0

        # Active conversations (non-terminal)
        placeholders = ",".join("?" * len(_TERMINAL_STATES))
        cursor = await db.execute(
            f"SELECT COUNT(*) AS total FROM conversations WHERE state NOT IN ({placeholders})",
            _TERMINAL_STATES,
        )
        row = await cursor.fetchone()
        active_conversations = row["total"] if row else 0

        # Successful conversations (GOT_NUMBER)
        cursor = await db.execute(
            "SELECT COUNT(*) AS total FROM conversations WHERE state = 'GOT_NUMBER'"
        )
        row = await cursor.fetchone()
        successful_conversations = row["total"] if row else 0

    today_quota = await get_today_quota()

    return {
        "total_universities": total_universities,
        "universities_with_ig": universities_with_ig,
        "universities_with_phone": universities_with_phone,
        "total_contacts": total_contacts,
        "total_conversations": total_conversations,
        "active_conversations": active_conversations,
        "successful_conversations": successful_conversations,
        "today_messages_sent": today_quota.get("messages_sent", 0),
        "today_conversations_started": today_quota.get("conversations_started", 0),
        "daily_conversation_limit": cfg.MAX_DAILY_CONVERSATIONS,
        "status_counts": status_counts,
    }


# ---------------------------------------------------------------------------
# Agent reasoning
# ---------------------------------------------------------------------------


async def update_agent_reasoning(conv_id: int, reasoning: str) -> None:
    """Update the agent_reasoning column for a conversation."""
    async with get_db() as db:
        await db.execute(
            "UPDATE conversations SET agent_reasoning = ? WHERE id = ?",
            (reasoning, conv_id),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Conversation analyses
# ---------------------------------------------------------------------------


async def search_conversations_for_learning(
    province: str | None = None,
    outcome: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Search completed conversations by province/outcome for learning."""
    conditions = [f"c.state IN ({','.join('?' * len(_TERMINAL_STATES))})"]
    params: list[Any] = list(_TERMINAL_STATES)

    if province:
        conditions.append("u.province = ?")
        params.append(province)
    if outcome:
        conditions.append("c.state = ?")
        params.append(outcome)

    where = " AND ".join(conditions)
    params.append(limit)

    async with get_db() as db:
        cursor = await db.execute(
            f"""
            SELECT c.*, u.name AS university_name, u.province,
                   ca.summary, ca.effective_strategies, ca.failure_factors,
                   ca.contact_personality, ca.recommended_improvements
            FROM conversations c
            LEFT JOIN universities u ON u.id = c.university_id
            LEFT JOIN conversation_analyses ca ON ca.conversation_id = c.id
            WHERE {where}
            ORDER BY c.last_message_at DESC
            LIMIT ?
            """,
            params,
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# Contact memory (persistent per-contact notes)
# ---------------------------------------------------------------------------


async def add_contact_memory(
    phone: str,
    memory_text: str,
    memory_type: str = "general",
) -> int:
    """Store a new persistent memory note about a contact."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO contact_memory (phone, memory_text, memory_type, created_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (phone, memory_text, memory_type),
        )
        await db.commit()
        return cursor.lastrowid


async def get_contact_memories(
    phone: str,
    limit: int = 10,
) -> list[dict]:
    """Return stored memory notes for a contact, newest first."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, phone, memory_text, memory_type, created_at
            FROM contact_memory
            WHERE phone = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (phone, limit),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def save_conversation_analysis(data: dict) -> int:
    """Insert a row into conversation_analyses and return the new id."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO conversation_analyses
                (conversation_id, outcome, total_messages, total_attempts,
                 duration_hours, province, success_factors, failure_factors,
                 contact_personality, effective_strategies,
                 recommended_improvements, summary, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("conversation_id"),
                data.get("outcome"),
                data.get("total_messages"),
                data.get("total_attempts"),
                data.get("duration_hours"),
                data.get("province"),
                json.dumps(data.get("success_factors")) if data.get("success_factors") else None,
                json.dumps(data.get("failure_factors")) if data.get("failure_factors") else None,
                data.get("contact_personality"),
                json.dumps(data.get("effective_strategies")) if data.get("effective_strategies") else None,
                data.get("recommended_improvements"),
                data.get("summary"),
                data.get("source", "outreach"),
                _utcnow(),
            ),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def get_unprocessed_analyses(limit: int = 50) -> list[dict]:
    """Return conversation_analyses rows that haven't been processed yet."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM conversation_analyses WHERE processed = 0 ORDER BY created_at LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def mark_analyses_processed(ids: list[int]) -> None:
    """Mark the given conversation_analyses as processed."""
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    async with get_db() as db:
        await db.execute(
            f"UPDATE conversation_analyses SET processed = 1 WHERE id IN ({placeholders})",
            ids,
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Lessons CRUD
# ---------------------------------------------------------------------------


async def get_lessons_by_situation(
    situation_type: str,
    province: str | None = None,
    min_confidence: float = 0.3,
    limit: int = 5,
) -> list[dict]:
    """
    Get active lessons for a situation type.

    Returns province-specific lessons first, then general ones,
    sorted by confidence * success_rate descending.
    """
    params: list[Any] = [situation_type, min_confidence]
    province_clause = ""
    if province:
        province_clause = """
            CASE WHEN province = ? THEN 0
                 WHEN province IS NULL THEN 1
                 ELSE 2
            END,
        """
        params.insert(1, province)

    params.append(limit)

    async with get_db() as db:
        cursor = await db.execute(
            f"""
            SELECT * FROM lessons
            WHERE situation_type = ?
              AND is_active = 1
              AND confidence >= ?
            ORDER BY
                {province_clause}
                (confidence * success_rate) DESC
            LIMIT ?
            """,
            params,
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_all_active_lessons() -> list[dict]:
    """Return all active lessons."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM lessons WHERE is_active = 1 ORDER BY situation_type, confidence DESC"
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def create_lesson(data: dict) -> int:
    """Insert a new lesson and return its id."""
    async with get_db() as db:
        now = _utcnow()
        cursor = await db.execute(
            """
            INSERT INTO lessons
                (situation_type, insight, recommended_strategy, province,
                 success_rate, example_count, confidence, is_active,
                 source_analysis_ids, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("situation_type"),
                data.get("insight"),
                data.get("recommended_strategy"),
                data.get("province"),
                data.get("success_rate", 0),
                data.get("example_count", 0),
                data.get("confidence", 0.5),
                data.get("is_active", 1),
                json.dumps(data.get("source_analysis_ids")) if data.get("source_analysis_ids") else None,
                now,
                now,
            ),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def update_lesson(lesson_id: int, **kwargs) -> None:
    """Update specific fields of a lesson."""
    allowed = {
        "situation_type", "insight", "recommended_strategy", "province",
        "success_rate", "example_count", "confidence", "is_active",
        "source_analysis_ids",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return

    # JSON-encode source_analysis_ids if present
    if "source_analysis_ids" in updates and isinstance(updates["source_analysis_ids"], (list, dict)):
        updates["source_analysis_ids"] = json.dumps(updates["source_analysis_ids"])

    updates["updated_at"] = _utcnow()

    set_clauses = [f"{k} = ?" for k in updates]
    values = list(updates.values())
    values.append(lesson_id)

    async with get_db() as db:
        await db.execute(
            f"UPDATE lessons SET {', '.join(set_clauses)} WHERE id = ?",
            values,
        )
        await db.commit()


async def deactivate_lesson(lesson_id: int) -> None:
    """Set is_active=0 for a lesson."""
    async with get_db() as db:
        await db.execute(
            "UPDATE lessons SET is_active = 0, updated_at = ? WHERE id = ?",
            (_utcnow(), lesson_id),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Strategy metrics
# ---------------------------------------------------------------------------


async def save_strategy_metric(data: dict) -> int:
    """Insert a row into strategy_metrics and return the new id."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO strategy_metrics
                (conversation_id, strategy_used, situation_type, outcome,
                 province, response_time_minutes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("conversation_id"),
                data.get("strategy_used"),
                data.get("situation_type"),
                data.get("outcome"),
                data.get("province"),
                data.get("response_time_minutes"),
                _utcnow(),
            ),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def get_aggregated_strategy_metrics(since_days: int = 7) -> list[dict]:
    """
    Aggregate strategy_metrics grouped by strategy_used and situation_type
    for the last *since_days* days.
    """
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT
                strategy_used,
                situation_type,
                COUNT(*) AS total_uses,
                SUM(CASE WHEN outcome IN ('GOT_NUMBER', 'ZOOM_SENT', 'SCHEDULED') THEN 1 ELSE 0 END) AS successes,
                ROUND(AVG(response_time_minutes), 1) AS avg_response_minutes,
                ROUND(
                    CAST(SUM(CASE WHEN outcome IN ('GOT_NUMBER', 'ZOOM_SENT', 'SCHEDULED') THEN 1 ELSE 0 END) AS REAL)
                    / COUNT(*), 3
                ) AS success_rate
            FROM strategy_metrics
            WHERE created_at >= datetime('now', ?)
            GROUP BY strategy_used, situation_type
            ORDER BY total_uses DESC
            """,
            (f"-{since_days} days",),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# Config CRUD
# ---------------------------------------------------------------------------


async def get_all_config() -> dict[str, str]:
    """Return all rows from the config table as {key: value}."""
    async with get_db() as db:
        cursor = await db.execute("SELECT key, value FROM config")
        rows = await cursor.fetchall()
        return {r["key"]: r["value"] for r in rows}


async def upsert_config(key: str, value: str) -> None:
    """Insert or update a config key."""
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO config (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')
            """,
            (key, value),
        )
        await db.commit()


async def delete_config(key: str) -> None:
    """Delete a config key (resets to default)."""
    async with get_db() as db:
        await db.execute("DELETE FROM config WHERE key = ?", (key,))
        await db.commit()


# ---------------------------------------------------------------------------
# Auth CRUD
# ---------------------------------------------------------------------------


async def count_active_auth_roles() -> int:
    """Return the number of active auth role assignments."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) AS total FROM auth_user_roles WHERE is_active = 1"
        )
        row = await cursor.fetchone()
        return int(row["total"] if row else 0)


async def count_active_auth_role_assignments(role_key: str) -> int:
    """Return the number of active assignments for a specific local role."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT COUNT(*) AS total
            FROM auth_user_roles
            WHERE is_active = 1 AND role_key = ?
            """,
            (role_key,),
        )
        row = await cursor.fetchone()
        return int(row["total"] if row else 0)


async def get_auth_role_keys_for_user(dms_user_id: int) -> list[str]:
    """Return active local role keys assigned to a DMS user."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT role_key
            FROM auth_user_roles
            WHERE dms_user_id = ? AND is_active = 1
            ORDER BY role_key ASC
            """,
            (dms_user_id,),
        )
        rows = await cursor.fetchall()
        return [str(row["role_key"]) for row in rows]


async def list_auth_role_assignments() -> list[dict[str, Any]]:
    """Return all active local auth role assignments."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, dms_user_id, user_email, user_name, role_key,
                   granted_by_email, created_at, updated_at
            FROM auth_user_roles
            WHERE is_active = 1
            ORDER BY user_email ASC, role_key ASC
            """
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_active_auth_role_assignment(dms_user_id: int, role_key: str) -> dict[str, Any] | None:
    """Return one active role assignment for a user and role key."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, dms_user_id, user_email, user_name, role_key,
                   granted_by_email, created_at, updated_at
            FROM auth_user_roles
            WHERE dms_user_id = ? AND role_key = ? AND is_active = 1
            LIMIT 1
            """,
            (dms_user_id, role_key),
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def upsert_auth_user_role(
    dms_user_id: int,
    user_email: str,
    user_name: str,
    role_key: str,
    granted_by_email: str | None = None,
) -> None:
    """Create or reactivate a local role assignment for a DMS user."""
    now = _utcnow()
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO auth_user_roles (
                dms_user_id, user_email, user_name, role_key,
                is_active, granted_by_email, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(dms_user_id, role_key) DO UPDATE SET
                user_email = excluded.user_email,
                user_name = excluded.user_name,
                is_active = 1,
                granted_by_email = excluded.granted_by_email,
                updated_at = excluded.updated_at
            """,
            (dms_user_id, user_email, user_name, role_key, granted_by_email, now, now),
        )
        await db.commit()


async def deactivate_auth_user_role(dms_user_id: int, role_key: str) -> None:
    """Deactivate a local role assignment."""
    async with get_db() as db:
        await db.execute(
            """
            UPDATE auth_user_roles
            SET is_active = 0, updated_at = ?
            WHERE dms_user_id = ? AND role_key = ?
            """,
            (_utcnow(), dms_user_id, role_key),
        )
        await db.commit()


async def create_auth_session(
    session_hash: str,
    dms_user_id: int,
    user_email: str,
    user_name: str,
    dms_user_level: str | None,
    expires_at: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> None:
    """Persist a new authenticated browser session."""
    now = _utcnow()
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO auth_sessions (
                session_hash, dms_user_id, user_email, user_name, dms_user_level,
                expires_at, created_at, last_seen_at, user_agent, ip_address
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_hash,
                dms_user_id,
                user_email,
                user_name,
                dms_user_level,
                expires_at,
                now,
                now,
                user_agent,
                ip_address,
            ),
        )
        await db.commit()


async def get_auth_session(session_hash: str) -> dict[str, Any] | None:
    """Return an auth session by hash."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT session_hash, dms_user_id, user_email, user_name, dms_user_level,
                   expires_at, created_at, last_seen_at, revoked_at, user_agent, ip_address
            FROM auth_sessions
            WHERE session_hash = ?
            LIMIT 1
            """,
            (session_hash,),
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def touch_auth_session(session_hash: str) -> None:
    """Update last-seen timestamp for an active session."""
    async with get_db() as db:
        await db.execute(
            "UPDATE auth_sessions SET last_seen_at = ? WHERE session_hash = ?",
            (_utcnow(), session_hash),
        )
        await db.commit()


async def revoke_auth_session(session_hash: str) -> None:
    """Revoke a single auth session."""
    async with get_db() as db:
        await db.execute(
            "UPDATE auth_sessions SET revoked_at = ? WHERE session_hash = ?",
            (_utcnow(), session_hash),
        )
        await db.commit()


async def revoke_auth_sessions_for_user(dms_user_id: int) -> None:
    """Revoke all sessions for a DMS user."""
    async with get_db() as db:
        await db.execute(
            "UPDATE auth_sessions SET revoked_at = ? WHERE dms_user_id = ? AND revoked_at IS NULL",
            (_utcnow(), dms_user_id),
        )
        await db.commit()


async def create_auth_audit_log(
    action: str,
    actor_dms_user_id: int | None = None,
    actor_email: str | None = None,
    subject_dms_user_id: int | None = None,
    subject_email: str | None = None,
    role_key: str | None = None,
    success: bool = True,
    detail: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Persist an auth-related audit event."""
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO auth_audit_logs (
                action, actor_dms_user_id, actor_email, subject_dms_user_id,
                subject_email, role_key, success, detail, ip_address, user_agent, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action,
                actor_dms_user_id,
                actor_email,
                subject_dms_user_id,
                subject_email,
                role_key,
                1 if success else 0,
                detail,
                ip_address,
                user_agent,
                _utcnow(),
            ),
        )
        await db.commit()


async def count_auth_audit_logs() -> int:
    """Return total auth audit log rows."""
    async with get_db() as db:
        cursor = await db.execute("SELECT COUNT(*) AS total FROM auth_audit_logs")
        row = await cursor.fetchone()
        return int(row["total"] if row else 0)


async def list_auth_audit_logs(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """Return auth audit logs ordered from newest to oldest."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, action, actor_dms_user_id, actor_email, subject_dms_user_id,
                   subject_email, role_key, success, detail, ip_address, user_agent, created_at
            FROM auth_audit_logs
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = await cursor.fetchall()
        items = _rows_to_dicts(rows)
        for item in items:
            item["success"] = bool(item.get("success"))
        return items


async def get_auth_role_upgrade_request(request_id: int) -> dict[str, Any] | None:
    """Return one role-upgrade request by id."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, requester_dms_user_id, requester_email, requester_name,
                   current_role_key, requested_role_key, status, request_note,
                   reviewed_by_dms_user_id, reviewed_by_email, review_note,
                   reviewed_at, created_at, updated_at
            FROM auth_role_upgrade_requests
            WHERE id = ?
            LIMIT 1
            """,
            (request_id,),
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def get_pending_auth_role_upgrade_request_for_user(dms_user_id: int) -> dict[str, Any] | None:
    """Return the latest pending role-upgrade request for a requester."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, requester_dms_user_id, requester_email, requester_name,
                   current_role_key, requested_role_key, status, request_note,
                   reviewed_by_dms_user_id, reviewed_by_email, review_note,
                   reviewed_at, created_at, updated_at
            FROM auth_role_upgrade_requests
            WHERE requester_dms_user_id = ? AND status = 'pending'
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (dms_user_id,),
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def count_auth_role_upgrade_requests(status: str | None = None) -> int:
    """Return total role-upgrade requests, optionally filtered by status."""
    async with get_db() as db:
        if status:
            cursor = await db.execute(
                "SELECT COUNT(*) AS total FROM auth_role_upgrade_requests WHERE status = ?",
                (status,),
            )
        else:
            cursor = await db.execute(
                "SELECT COUNT(*) AS total FROM auth_role_upgrade_requests"
            )
        row = await cursor.fetchone()
        return int(row["total"] if row else 0)


async def list_auth_role_upgrade_requests(
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return role-upgrade requests ordered from newest to oldest."""
    async with get_db() as db:
        if status:
            cursor = await db.execute(
                """
                SELECT id, requester_dms_user_id, requester_email, requester_name,
                       current_role_key, requested_role_key, status, request_note,
                       reviewed_by_dms_user_id, reviewed_by_email, review_note,
                       reviewed_at, created_at, updated_at
                FROM auth_role_upgrade_requests
                WHERE status = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (status, limit, offset),
            )
        else:
            cursor = await db.execute(
                """
                SELECT id, requester_dms_user_id, requester_email, requester_name,
                       current_role_key, requested_role_key, status, request_note,
                       reviewed_by_dms_user_id, reviewed_by_email, review_note,
                       reviewed_at, created_at, updated_at
                FROM auth_role_upgrade_requests
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def list_auth_role_upgrade_requests_for_user(
    dms_user_id: int,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return recent role-upgrade requests created by a specific requester."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, requester_dms_user_id, requester_email, requester_name,
                   current_role_key, requested_role_key, status, request_note,
                   reviewed_by_dms_user_id, reviewed_by_email, review_note,
                   reviewed_at, created_at, updated_at
            FROM auth_role_upgrade_requests
            WHERE requester_dms_user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (dms_user_id, limit),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def create_auth_role_upgrade_request(
    requester_dms_user_id: int,
    requester_email: str,
    requester_name: str,
    current_role_key: str,
    requested_role_key: str,
    request_note: str | None = None,
) -> int:
    """Create a new pending role-upgrade request and return its id."""
    now = _utcnow()
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO auth_role_upgrade_requests (
                requester_dms_user_id, requester_email, requester_name,
                current_role_key, requested_role_key, status,
                request_note, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (
                requester_dms_user_id,
                requester_email,
                requester_name,
                current_role_key,
                requested_role_key,
                request_note,
                now,
                now,
            ),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def resolve_auth_role_upgrade_request(
    request_id: int,
    status: str,
    reviewed_by_dms_user_id: int,
    reviewed_by_email: str,
    review_note: str | None = None,
) -> None:
    """Mark a role-upgrade request as approved or rejected."""
    now = _utcnow()
    async with get_db() as db:
        await db.execute(
            """
            UPDATE auth_role_upgrade_requests
            SET status = ?,
                reviewed_by_dms_user_id = ?,
                reviewed_by_email = ?,
                review_note = ?,
                reviewed_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                reviewed_by_dms_user_id,
                reviewed_by_email,
                review_note,
                now,
                now,
                request_id,
            ),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Audiensi Conversations CRUD
# ---------------------------------------------------------------------------

_AUDIENSI_TERMINAL_STATES = ("ZOOM_SENT", "REFUSED", "ABANDONED")


async def create_audiensi_conversation(
    university_id: int,
    source_conversation_id: int | None,
    contact_phone: str,
    contact_role: str | None = None,
    rector_name: str | None = None,
) -> int:
    """Create audiensi conversation, return new id."""
    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO audiensi_conversations
               (university_id, source_conversation_id, contact_phone, contact_role, rector_name, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (university_id, source_conversation_id, contact_phone, contact_role, rector_name, _utcnow()),
        )
        await db.commit()
        return cursor.lastrowid


async def get_audiensi_conversation_by_id(aud_id: int) -> dict | None:
    """Return a single audiensi conversation by ID with university name."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT a.*, u.name AS university_name, u.province
               FROM audiensi_conversations a
               LEFT JOIN universities u ON u.id = a.university_id
               WHERE a.id = ?""",
            (aud_id,),
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def get_audiensi_conversation_by_phone(phone: str) -> dict | None:
    """Return latest non-terminal audiensi conversation for a phone."""
    placeholders = ",".join("?" * len(_AUDIENSI_TERMINAL_STATES))
    async with get_db() as db:
        cursor = await db.execute(
            f"""SELECT a.*, u.name AS university_name
                FROM audiensi_conversations a
                LEFT JOIN universities u ON u.id = a.university_id
                WHERE a.contact_phone = ? AND a.state NOT IN ({placeholders})
                ORDER BY a.created_at DESC LIMIT 1""",
            (phone, *_AUDIENSI_TERMINAL_STATES),
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def get_audiensi_conversations_filtered(
    state: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Return audiensi conversations with optional state filter."""
    conditions = []
    params: list = []
    if state:
        conditions.append("a.state = ?")
        params.append(state)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    async with get_db() as db:
        cursor = await db.execute(
            f"""SELECT a.*, u.name AS university_name
                FROM audiensi_conversations a
                LEFT JOIN universities u ON u.id = a.university_id
                {where}
                ORDER BY a.created_at DESC
                LIMIT ? OFFSET ?""",
            (*params, limit, offset),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def update_audiensi_state(aud_id: int, state: str, **kwargs) -> None:
    """Update state of audiensi conversation plus optional extra fields."""
    allowed_fields = {
        "message_history", "pdf_path", "initial_message_draft",
        "scheduled_datetime", "zoom_link", "agent_reasoning",
        "attempt_count", "followup_count", "last_message_at",
        "approved_at", "approved_by", "contact_role", "rector_name",
    }
    extra = {k: v for k, v in kwargs.items() if k in allowed_fields}
    set_clauses = ["state = ?"]
    values: list[Any] = [state]
    for field, value in extra.items():
        set_clauses.append(f"{field} = ?")
        values.append(value)
    values.append(aud_id)
    sql = f"UPDATE audiensi_conversations SET {', '.join(set_clauses)} WHERE id = ?"
    async with get_db() as db:
        await db.execute(sql, values)
        await db.commit()


async def add_audiensi_message(aud_id: int, role: str, content: str) -> None:
    """Append a message to audiensi conversation's message_history JSON."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT message_history FROM audiensi_conversations WHERE id = ?",
            (aud_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            log.warning("add_audiensi_message: audiensi %d not found", aud_id)
            return
        history: list[dict] = json.loads(row["message_history"] or "[]")
        history.append({"role": role, "content": content, "timestamp": _utcnow()})
        await db.execute(
            "UPDATE audiensi_conversations SET message_history = ?, last_message_at = ? WHERE id = ?",
            (json.dumps(history), _utcnow(), aud_id),
        )
        await db.commit()


async def get_queued_audiensi() -> list[dict]:
    """Return audiensi conversations in QUEUED state for approval queue."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT a.*, u.name AS university_name, u.province
               FROM audiensi_conversations a
               LEFT JOIN universities u ON u.id = a.university_id
               WHERE a.state = 'QUEUED'
               ORDER BY a.created_at""",
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_active_audiensi() -> list[dict]:
    """Return non-terminal audiensi conversations."""
    placeholders = ",".join("?" * len(_AUDIENSI_TERMINAL_STATES))
    async with get_db() as db:
        cursor = await db.execute(
            f"""SELECT a.*, u.name AS university_name
                FROM audiensi_conversations a
                LEFT JOIN universities u ON u.id = a.university_id
                WHERE a.state NOT IN ({placeholders})
                ORDER BY a.last_message_at DESC NULLS LAST""",
            _AUDIENSI_TERMINAL_STATES,
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_audiensi_stats() -> dict:
    """Return aggregate counts for audiensi dashboard."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT state, COUNT(*) AS count FROM audiensi_conversations GROUP BY state"
        )
        rows = await cursor.fetchall()
        state_counts = {r["state"]: r["count"] for r in rows}
        cursor = await db.execute("SELECT COUNT(*) AS total FROM audiensi_conversations")
        row = await cursor.fetchone()
        total = row["total"] if row else 0
    return {
        "total": total,
        "queued": state_counts.get("QUEUED", 0),
        "approved": state_counts.get("APPROVED", 0),
        "in_progress": sum(state_counts.get(s, 0) for s in ("INITIAL_SENT", "WAITING_REPLY", "REPLIED", "ANALYZING", "SCHEDULING", "NEED_MORE", "FOLLOWUP_SENT")),
        "scheduled": state_counts.get("SCHEDULED", 0),
        "completed": state_counts.get("ZOOM_SENT", 0),
        "refused": state_counts.get("REFUSED", 0),
        "abandoned": state_counts.get("ABANDONED", 0),
        "state_counts": state_counts,
    }


async def update_university_rector_name(uni_id: int, rector_name: str) -> None:
    """Update rector_name on universities table."""
    async with get_db() as db:
        await db.execute(
            "UPDATE universities SET rector_name = ? WHERE id = ?",
            (rector_name, uni_id),
        )
        await db.commit()


async def get_audiensi_by_source_conversation_id(conv_id: int) -> dict | None:
    """Return audiensi conversation linked to a source outreach conversation."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT a.id, a.state, a.scheduled_datetime, a.zoom_link, a.created_at,
                      u.name AS university_name
               FROM audiensi_conversations a
               LEFT JOIN universities u ON u.id = a.university_id
               WHERE a.source_conversation_id = ?
               ORDER BY a.created_at DESC LIMIT 1""",
            (conv_id,),
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def get_audiensi_needing_followup(hours_threshold: int) -> list[dict]:
    """Return audiensi conversations needing follow-up."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT a.*, u.name AS university_name
               FROM audiensi_conversations a
               LEFT JOIN universities u ON u.id = a.university_id
               WHERE a.state IN ('WAITING_REPLY', 'FOLLOWUP_SENT')
                 AND a.last_message_at IS NOT NULL
                 AND (julianday('now') - julianday(a.last_message_at)) * 24 >= ?
               ORDER BY a.last_message_at""",
            (hours_threshold,),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# Knowledge Items CRUD
# ---------------------------------------------------------------------------


async def get_knowledge_items(
    chatbot_type: str | None = None, active_only: bool = False
) -> list[dict]:
    """Return knowledge items, optionally filtered by chatbot_type and active status."""
    conditions: list[str] = []
    params: list = []
    if chatbot_type:
        conditions.append("chatbot_type = ?")
        params.append(chatbot_type)
    if active_only:
        conditions.append("is_active = 1")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    async with get_db() as db:
        cursor = await db.execute(
            f"SELECT * FROM knowledge_items {where} ORDER BY created_at DESC",
            params,
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_knowledge_items_by_tags(
    chatbot_type: str, tags: list[str], active_only: bool = True
) -> list[dict]:
    """Fetch knowledge items whose situation_tags overlap with the given tags."""
    if not tags:
        return []
    conditions = ["chatbot_type = ?"]
    params: list = [chatbot_type]
    if active_only:
        conditions.append("is_active = 1")
    # Match any tag via OR of LIKE clauses
    tag_clauses = []
    for tag in tags:
        tag_clauses.append("situation_tags LIKE ?")
        params.append(f"%{tag}%")
    conditions.append(f"({' OR '.join(tag_clauses)})")
    where = " AND ".join(conditions)
    async with get_db() as db:
        cursor = await db.execute(
            f"SELECT * FROM knowledge_items WHERE {where} ORDER BY created_at DESC",
            params,
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_knowledge_item_by_id(item_id: int) -> dict | None:
    """Return a single knowledge item by ID."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM knowledge_items WHERE id = ?", (item_id,)
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def create_knowledge_item(
    chatbot_type: str, title: str, content: str,
    situation_tags: str = "", trigger_keywords: str = "",
) -> int:
    """Insert a knowledge item and return its id."""
    now = _utcnow()
    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO knowledge_items (chatbot_type, title, content, situation_tags, trigger_keywords, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (chatbot_type, title, content, situation_tags, trigger_keywords, now, now),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def match_knowledge_items_by_message(
    chatbot_type: str, message: str,
) -> list[dict]:
    """Match knowledge items against a message using trigger_keywords.

    Matching rules:
    - Items with trigger_keywords: inject if ANY keyword appears in the message
    - Items with situation_tags containing 'tone_umum' but no trigger_keywords: always inject
    - Items with neither trigger_keywords nor 'tone_umum' tag: skip

    This replaces the old flow of hardcoded detector -> tag lookup.
    """
    all_items = await get_knowledge_items(chatbot_type, active_only=True)
    msg_lower = message.lower()
    matched: list[dict] = []

    for item in all_items:
        trigger_kw = (item.get("trigger_keywords") or "").strip()
        sit_tags = (item.get("situation_tags") or "").strip()

        if trigger_kw:
            # Check if any trigger keyword appears in the message
            keywords = [kw.strip().lower() for kw in trigger_kw.split(",") if kw.strip()]
            if any(kw in msg_lower for kw in keywords):
                matched.append(item)
        elif "tone_umum" in sit_tags:
            # Always inject tone_umum items (no keywords needed)
            matched.append(item)
        # else: item has no trigger_keywords and no tone_umum tag → skip

    return matched


async def update_knowledge_item(item_id: int, **kwargs) -> None:
    """Update specific fields of a knowledge item."""
    allowed = {"title", "content", "is_active", "situation_tags", "trigger_keywords"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = _utcnow()
    set_clauses = [f"{k} = ?" for k in updates]
    values = list(updates.values())
    values.append(item_id)
    async with get_db() as db:
        await db.execute(
            f"UPDATE knowledge_items SET {', '.join(set_clauses)} WHERE id = ?",
            values,
        )
        await db.commit()


async def delete_knowledge_item(item_id: int) -> None:
    """Delete a knowledge item."""
    async with get_db() as db:
        await db.execute("DELETE FROM knowledge_items WHERE id = ?", (item_id,))
        await db.commit()


# ---------------------------------------------------------------------------
# API Call Logs
# ---------------------------------------------------------------------------


async def save_api_call_log(data: dict) -> int:
    """Insert a row into api_call_logs and return the new id."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO api_call_logs
                (conversation_id, chatbot_type, call_type, situation_tags,
                 knowledge_items_injected, system_prompt, messages_sent,
                 model_used, tool_calls_made, response_text,
                 prompt_tokens, completion_tokens, total_tokens, cached_tokens, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("conversation_id"),
                data.get("chatbot_type", "agent"),
                data.get("call_type", "reply"),
                json.dumps(data.get("situation_tags", [])),
                json.dumps(data.get("knowledge_items_injected", [])),
                data.get("system_prompt"),
                json.dumps(data.get("messages_sent")) if data.get("messages_sent") else None,
                data.get("model_used"),
                json.dumps(data.get("tool_calls_made", [])),
                data.get("response_text"),
                data.get("prompt_tokens", 0),
                data.get("completion_tokens", 0),
                data.get("total_tokens", 0),
                data.get("cached_tokens", 0),
                _utcnow(),
            ),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def get_api_call_logs(
    chatbot_type: str | None = None,
    conversation_id: int | None = None,
    call_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Return api_call_logs list (excludes system_prompt and messages_sent for brevity)."""
    conditions: list[str] = []
    params: list = []
    if chatbot_type:
        conditions.append("chatbot_type = ?")
        params.append(chatbot_type)
    if conversation_id is not None:
        conditions.append("conversation_id = ?")
        params.append(conversation_id)
    if call_type:
        conditions.append("call_type = ?")
        params.append(call_type)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    async with get_db() as db:
        cursor = await db.execute(
            f"""
            SELECT id, conversation_id, chatbot_type, call_type,
                   situation_tags, knowledge_items_injected, model_used,
                   tool_calls_made, response_text,
                   prompt_tokens, completion_tokens, total_tokens, cached_tokens, created_at
            FROM api_call_logs
            {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


async def get_api_call_log_by_id(log_id: int) -> dict | None:
    """Return a full api_call_log row by ID (including system_prompt & messages_sent)."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM api_call_logs WHERE id = ?", (log_id,)
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def update_last_response_id(table: str, row_id: int, response_id: str) -> None:
    """Save a Responses API response_id for session chaining."""
    if table not in ("conversations", "audiensi_conversations"):
        raise ValueError(f"Invalid table: {table}")
    async with get_db() as db:
        await db.execute(
            f"UPDATE {table} SET last_response_id = ? WHERE id = ?",
            (response_id, row_id),
        )
        await db.commit()


async def clear_last_response_id(table: str, row_id: int) -> None:
    """Clear last_response_id when session needs to be invalidated."""
    if table not in ("conversations", "audiensi_conversations"):
        raise ValueError(f"Invalid table: {table}")
    async with get_db() as db:
        await db.execute(
            f"UPDATE {table} SET last_response_id = NULL WHERE id = ?",
            (row_id,),
        )
        await db.commit()


async def clear_all_response_ids(table: str) -> None:
    """Clear all last_response_id values (e.g. when knowledge base changes)."""
    if table not in ("conversations", "audiensi_conversations"):
        raise ValueError(f"Invalid table: {table}")
    async with get_db() as db:
        await db.execute(
            f"UPDATE {table} SET last_response_id = NULL WHERE last_response_id IS NOT NULL"
        )
        await db.commit()


async def cleanup_old_api_logs(days: int = 7) -> int:
    """Delete api_call_logs older than *days* days. Return count deleted."""
    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM api_call_logs WHERE created_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        await db.commit()
        return cursor.rowcount


# ---------------------------------------------------------------------------
# Pipeline activity logs
# ---------------------------------------------------------------------------


async def create_pipeline_log(
    agent_type: str,
    trigger_type: str = "manual",
) -> int:
    """Create a new 'running' pipeline log entry. Return its id."""
    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO pipeline_logs (agent_type, trigger_type, status, started_at)
               VALUES (?, ?, 'running', ?)""",
            (agent_type, trigger_type, now),
        )
        await db.commit()
        return cursor.lastrowid


async def complete_pipeline_log(
    log_id: int,
    *,
    status: str = "completed",
    summary: dict | None = None,
    details: list | None = None,
    error: str | None = None,
    items_processed: int = 0,
    items_success: int = 0,
    items_failed: int = 0,
) -> None:
    """Mark a pipeline log entry as completed (or failed)."""
    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        # Fetch started_at to compute duration
        cursor = await db.execute(
            "SELECT started_at FROM pipeline_logs WHERE id = ?", (log_id,)
        )
        row = await cursor.fetchone()
        duration = None
        if row:
            try:
                started = datetime.fromisoformat(row[0])
                ended = datetime.fromisoformat(now)
                # Make both offset-aware for subtraction
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                if ended.tzinfo is None:
                    ended = ended.replace(tzinfo=timezone.utc)
                duration = (ended - started).total_seconds()
            except Exception:
                pass

        await db.execute(
            """UPDATE pipeline_logs
               SET status = ?, completed_at = ?, duration_seconds = ?,
                   summary = ?, details = ?, error = ?,
                   items_processed = ?, items_success = ?, items_failed = ?
               WHERE id = ?""",
            (
                status,
                now,
                duration,
                json.dumps(summary) if summary else None,
                json.dumps(details) if details else None,
                error,
                items_processed,
                items_success,
                items_failed,
                log_id,
            ),
        )
        await db.commit()


async def get_pipeline_logs(
    agent_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Return paginated pipeline logs with optional filters."""
    async with get_db() as db:
        conditions = []
        params: list[Any] = []
        if agent_type:
            conditions.append("agent_type = ?")
            params.append(agent_type)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        # Count
        count_row = await (
            await db.execute(f"SELECT COUNT(*) FROM pipeline_logs {where}", params)
        ).fetchone()
        total = count_row[0] if count_row else 0

        # Data
        params_data = params + [limit, offset]
        cursor = await db.execute(
            f"""SELECT * FROM pipeline_logs {where}
                ORDER BY started_at DESC LIMIT ? OFFSET ?""",
            params_data,
        )
        rows = await cursor.fetchall()
        items = []
        for r in rows:
            d = _row_to_dict(r)
            # Parse JSON fields
            for field in ("summary", "details"):
                if d.get(field) and isinstance(d[field], str):
                    try:
                        d[field] = json.loads(d[field])
                    except Exception:
                        pass
            items.append(d)

        return {"items": items, "total": total}


async def get_pipeline_log_by_id(log_id: int) -> dict | None:
    """Return a single pipeline log entry by id."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM pipeline_logs WHERE id = ?", (log_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        d = _row_to_dict(row)
        for field in ("summary", "details"):
            if d.get(field) and isinstance(d[field], str):
                try:
                    d[field] = json.loads(d[field])
                except Exception:
                    pass
        return d


async def cleanup_old_pipeline_logs(days: int = 30) -> int:
    """Delete pipeline_logs older than *days* days. Return count deleted."""
    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM pipeline_logs WHERE started_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        await db.commit()
        return cursor.rowcount


# ---------------------------------------------------------------------------
# IG Accounts CRUD
# ---------------------------------------------------------------------------


async def get_ig_accounts(enabled_only: bool = False) -> list[dict]:
    """Return all IG accounts. If *enabled_only*, filter by enabled=1."""
    async with get_db() as db:
        if enabled_only:
            cursor = await db.execute(
                "SELECT * FROM ig_accounts WHERE enabled = 1 ORDER BY id"
            )
        else:
            cursor = await db.execute("SELECT * FROM ig_accounts ORDER BY id")
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]


async def create_ig_account(username: str, password: str, notes: str = "") -> dict:
    """Insert a new IG account. Returns the created row."""
    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO ig_accounts (username, password, notes)
               VALUES (?, ?, ?)""",
            (username.strip().lower(), password, notes),
        )
        await db.commit()
        row_id = cursor.lastrowid
        cursor = await db.execute("SELECT * FROM ig_accounts WHERE id = ?", (row_id,))
        row = await cursor.fetchone()
        return _row_to_dict(row)


async def update_ig_account(
    account_id: int, *, username: str | None = None,
    password: str | None = None, enabled: bool | None = None,
    notes: str | None = None, **kwargs,
) -> dict | None:
    """Update fields of an IG account. Returns updated row or None."""
    sets: list[str] = []
    vals: list = []
    if username is not None:
        sets.append("username = ?")
        vals.append(username.strip().lower())
    if password is not None:
        sets.append("password = ?")
        vals.append(password)
    if enabled is not None:
        sets.append("enabled = ?")
        vals.append(1 if enabled else 0)
    if notes is not None:
        sets.append("notes = ?")
        vals.append(notes)
    if kwargs.get("login_status") is not None:
        sets.append("login_status = ?")
        vals.append(kwargs["login_status"])
    if kwargs.get("last_login_test") is not None:
        sets.append("last_login_test = ?")
        vals.append(kwargs["last_login_test"])
    if not sets:
        return None
    sets.append("updated_at = datetime('now')")
    vals.append(account_id)
    async with get_db() as db:
        await db.execute(
            f"UPDATE ig_accounts SET {', '.join(sets)} WHERE id = ?", vals
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM ig_accounts WHERE id = ?", (account_id,))
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def delete_ig_account(account_id: int) -> bool:
    """Delete an IG account. Returns True if deleted."""
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM ig_accounts WHERE id = ?", (account_id,))
        await db.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# OSINT CRUD
# ---------------------------------------------------------------------------


async def upsert_osint_profile(university_id: int, **kwargs) -> int:
    """Insert or update an OSINT profile for a university. Returns the profile id."""
    allowed = {
        "address", "city", "province", "postal_code", "phone_official", "fax",
        "email_official", "website_verified", "vision_mission", "faculty_count",
        "faculty_list", "org_structure", "confidence", "last_run_id",
    }
    data = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM osint_profiles WHERE university_id = ?", (university_id,)
        )
        existing = await cursor.fetchone()
        if existing:
            if data:
                sets = ", ".join(f"{k} = ?" for k in data)
                vals = list(data.values()) + [university_id]
                await db.execute(
                    f"UPDATE osint_profiles SET {sets}, updated_at = datetime('now') WHERE university_id = ?",
                    vals,
                )
                await db.commit()
            return existing["id"]
        else:
            cols = ["university_id"] + list(data.keys())
            placeholders = ", ".join("?" for _ in cols)
            vals = [university_id] + list(data.values())
            cursor = await db.execute(
                f"INSERT INTO osint_profiles ({', '.join(cols)}) VALUES ({placeholders})",
                vals,
            )
            await db.commit()
            return cursor.lastrowid


async def get_osint_profile(university_id: int) -> dict | None:
    """Get the OSINT profile for a university."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM osint_profiles WHERE university_id = ?", (university_id,)
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def upsert_osint_contact(university_id: int, name: str | None, phone: str | None, **kwargs) -> int:
    """Insert or update an OSINT contact. Returns the contact id."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM osint_contacts WHERE university_id = ? AND phone = ? AND name = ?",
            (university_id, phone, name),
        )
        existing = await cursor.fetchone()
        if existing:
            return existing["id"]
        allowed = {"title", "department", "email", "source", "source_url", "confidence", "priority", "verified"}
        data = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        cols = ["university_id", "name", "phone"] + list(data.keys())
        placeholders = ", ".join("?" for _ in cols)
        vals = [university_id, name, phone] + list(data.values())
        cursor = await db.execute(
            f"INSERT OR IGNORE INTO osint_contacts ({', '.join(cols)}) VALUES ({placeholders})",
            vals,
        )
        await db.commit()
        return cursor.lastrowid


async def get_osint_contacts(university_id: int) -> list[dict]:
    """List all OSINT contacts for a university, ordered by priority."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM osint_contacts WHERE university_id = ? ORDER BY priority DESC, confidence DESC",
            (university_id,),
        )
        return _rows_to_dicts(await cursor.fetchall())


async def upsert_osint_social(university_id: int, platform: str, handle: str, **kwargs) -> int:
    """Insert or update an OSINT social media entry."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM osint_social_media WHERE university_id = ? AND platform = ? AND handle = ?",
            (university_id, platform, handle),
        )
        existing = await cursor.fetchone()
        if existing:
            return existing["id"]
        allowed = {"url", "followers", "verified", "confidence", "source"}
        data = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        cols = ["university_id", "platform", "handle"] + list(data.keys())
        placeholders = ", ".join("?" for _ in cols)
        vals = [university_id, platform, handle] + list(data.values())
        cursor = await db.execute(
            f"INSERT OR IGNORE INTO osint_social_media ({', '.join(cols)}) VALUES ({placeholders})",
            vals,
        )
        await db.commit()
        return cursor.lastrowid


async def get_osint_social(university_id: int) -> list[dict]:
    """List all OSINT social media entries for a university."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM osint_social_media WHERE university_id = ? ORDER BY platform",
            (university_id,),
        )
        return _rows_to_dicts(await cursor.fetchall())


async def add_osint_news(university_id: int, title: str, **kwargs) -> int:
    """Insert a news item for a university."""
    allowed = {"summary", "url", "source", "published_date", "category", "relevance_score"}
    data = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    cols = ["university_id", "title"] + list(data.keys())
    placeholders = ", ".join("?" for _ in cols)
    vals = [university_id, title] + list(data.values())
    async with get_db() as db:
        cursor = await db.execute(
            f"INSERT INTO osint_news ({', '.join(cols)}) VALUES ({placeholders})",
            vals,
        )
        await db.commit()
        return cursor.lastrowid


async def get_osint_news(university_id: int, limit: int = 20) -> list[dict]:
    """List recent news for a university."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM osint_news WHERE university_id = ? ORDER BY created_at DESC LIMIT ?",
            (university_id, limit),
        )
        return _rows_to_dicts(await cursor.fetchall())


async def create_osint_run(university_id: int, trigger_type: str = "manual") -> int:
    """Create an OSINT run log entry. Returns the run id."""
    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO osint_runs (university_id, trigger_type) VALUES (?, ?)",
            (university_id, trigger_type),
        )
        await db.commit()
        return cursor.lastrowid


async def update_osint_run(run_id: int, **kwargs) -> None:
    """Update an OSINT run log entry."""
    allowed = {
        "status", "agents_completed", "agents_failed", "contacts_found",
        "social_media_found", "news_found", "duration_seconds", "error", "completed_at",
    }
    data = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not data:
        return
    sets = ", ".join(f"{k} = ?" for k in data)
    vals = list(data.values()) + [run_id]
    async with get_db() as db:
        await db.execute(f"UPDATE osint_runs SET {sets} WHERE id = ?", vals)
        await db.commit()


async def get_osint_runs(university_id: int | None = None, limit: int = 20) -> list[dict]:
    """List OSINT run logs, optionally filtered by university."""
    async with get_db() as db:
        if university_id:
            cursor = await db.execute(
                "SELECT * FROM osint_runs WHERE university_id = ? ORDER BY started_at DESC LIMIT ?",
                (university_id, limit),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM osint_runs ORDER BY started_at DESC LIMIT ?", (limit,)
            )
        return _rows_to_dicts(await cursor.fetchall())


async def get_osint_run(run_id: int) -> dict | None:
    """Get a single OSINT run by id."""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM osint_runs WHERE id = ?", (run_id,))
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


# ---------------------------------------------------------------------------
# CRM / PIC Profiling CRUD
# ---------------------------------------------------------------------------


async def create_crm_request(
    pic_name: str,
    university_id: int | None = None,
    university_name: str | None = None,
    pic_title: str | None = None,
    requested_by: str | None = None,
    priority: str = "normal",
    notes: str | None = None,
) -> int:
    """Create a new CRM profiling request. Returns the request id."""
    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO crm_requests
               (university_id, university_name, pic_name, pic_title, requested_by, priority, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (university_id, university_name, pic_name, pic_title, requested_by, priority, notes),
        )
        await db.commit()
        return cursor.lastrowid


async def get_crm_requests(
    status: str | None = None,
    limit: int = 25,
    offset: int = 0,
) -> dict:
    """List CRM requests with optional status filter. Returns {requests, total}."""
    async with get_db() as db:
        where = "WHERE status = ?" if status else ""
        params_count: tuple = (status,) if status else ()
        cursor = await db.execute(
            f"SELECT COUNT(*) as cnt FROM crm_requests {where}", params_count
        )
        total = (await cursor.fetchone())["cnt"]

        params: tuple = (*params_count, limit, offset)
        cursor = await db.execute(
            f"SELECT * FROM crm_requests {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        )
        rows = _rows_to_dicts(await cursor.fetchall())
        return {"requests": rows, "total": total}


async def get_crm_request(request_id: int) -> dict | None:
    """Get a single CRM request by id."""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM crm_requests WHERE id = ?", (request_id,))
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def update_crm_request_status(request_id: int, status: str, run_id: int | None = None) -> None:
    """Update CRM request status."""
    async with get_db() as db:
        if run_id is not None:
            await db.execute(
                "UPDATE crm_requests SET status = ?, run_id = ?, updated_at = datetime('now') WHERE id = ?",
                (status, run_id, request_id),
            )
        else:
            await db.execute(
                "UPDATE crm_requests SET status = ?, updated_at = datetime('now') WHERE id = ?",
                (status, request_id),
            )
        await db.commit()


async def create_crm_profile(request_id: int, university_id: int | None = None, **kwargs) -> int:
    """Create a PIC profile. Returns the profile id."""
    allowed = {
        "full_name", "full_name_source", "title", "title_source",
        "teaching_subjects", "teaching_subjects_source", "tenure_years", "tenure_years_source",
        "birth_date", "birth_date_source", "age", "origin_region", "origin_region_source",
        "education_history", "education_history_source", "photo_url",
        "marital_status", "marital_status_source", "spouse_name", "spouse_name_source",
        "children_count", "children_count_source", "family_residence", "family_residence_source",
        "campus_problems", "campus_problems_source", "campus_concerns", "campus_concerns_source",
        "campus_hopes", "campus_hopes_source",
        "hobbies", "hobbies_source", "favorite_food", "favorite_food_source",
        "outside_activities", "outside_activities_source",
        "personality_summary", "recent_topics", "communication_style", "social_behavior_insights",
        "linkedin_url", "instagram_handle", "facebook_url", "twitter_handle", "other_social",
        "home_address", "home_address_source", "phone", "email",
        "overall_confidence", "fields_found", "fields_total", "fields_manual",
    }
    data = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    cols = ["request_id", "university_id"] + list(data.keys())
    placeholders = ", ".join("?" for _ in cols)
    vals = [request_id, university_id] + list(data.values())
    async with get_db() as db:
        cursor = await db.execute(
            f"INSERT INTO crm_pic_profiles ({', '.join(cols)}) VALUES ({placeholders})",
            vals,
        )
        await db.commit()
        return cursor.lastrowid


async def get_crm_profile_by_request(request_id: int) -> dict | None:
    """Get the latest PIC profile associated with a CRM request."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM crm_pic_profiles WHERE request_id = ? ORDER BY id DESC LIMIT 1", (request_id,)
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def get_crm_profile(profile_id: int) -> dict | None:
    """Get a PIC profile by id."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM crm_pic_profiles WHERE id = ?", (profile_id,)
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def update_crm_profile(profile_id: int, source_type: str = "manual", **kwargs) -> dict | None:
    """Update fields on a PIC profile. Automatically records sources for each updated field."""
    allowed = {
        "full_name", "title", "teaching_subjects", "tenure_years",
        "birth_date", "age", "origin_region", "education_history", "photo_url",
        "marital_status", "spouse_name", "children_count", "family_residence",
        "campus_problems", "campus_concerns", "campus_hopes",
        "hobbies", "favorite_food", "outside_activities",
        "personality_summary", "recent_topics", "communication_style", "social_behavior_insights",
        "linkedin_url", "instagram_handle", "facebook_url", "twitter_handle", "other_social",
        "home_address", "phone", "email",
        "overall_confidence", "fields_found", "fields_total", "fields_manual",
    }
    data = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not data:
        return None
    # Also set source columns for fields that have them
    source_fields = {}
    for k in list(data.keys()):
        src_col = f"{k}_source"
        if src_col in {
            "full_name_source", "title_source", "teaching_subjects_source",
            "tenure_years_source", "birth_date_source", "origin_region_source",
            "education_history_source", "marital_status_source", "spouse_name_source",
            "children_count_source", "family_residence_source",
            "campus_problems_source", "campus_concerns_source", "campus_hopes_source",
            "hobbies_source", "favorite_food_source", "outside_activities_source",
            "home_address_source",
        }:
            source_fields[src_col] = source_type
    data.update(source_fields)
    sets = ", ".join(f"{k} = ?" for k in data)
    vals = list(data.values()) + [profile_id]
    async with get_db() as db:
        await db.execute(
            f"UPDATE crm_pic_profiles SET {sets}, last_updated = datetime('now') WHERE id = ?",
            vals,
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT * FROM crm_pic_profiles WHERE id = ?", (profile_id,)
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def add_crm_profile_source(profile_id: int, field_name: str, value: str, source_type: str, **kwargs) -> int:
    """Add an audit trail entry for a profile field."""
    allowed = {"source_url", "confidence", "notes"}
    data = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    cols = ["profile_id", "field_name", "value", "source_type"] + list(data.keys())
    placeholders = ", ".join("?" for _ in cols)
    vals = [profile_id, field_name, value, source_type] + list(data.values())
    async with get_db() as db:
        cursor = await db.execute(
            f"INSERT INTO crm_profile_sources ({', '.join(cols)}) VALUES ({placeholders})",
            vals,
        )
        await db.commit()
        return cursor.lastrowid


async def get_crm_profile_sources(profile_id: int) -> list[dict]:
    """Get all source audit trail entries for a profile."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM crm_profile_sources WHERE profile_id = ? ORDER BY created_at DESC",
            (profile_id,),
        )
        return _rows_to_dicts(await cursor.fetchall())


async def create_crm_profile_run(request_id: int) -> int:
    """Create a CRM profiling run log. Returns the run id."""
    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO crm_profile_runs (request_id) VALUES (?)", (request_id,)
        )
        await db.commit()
        return cursor.lastrowid


async def update_crm_profile_run(run_id: int, **kwargs) -> None:
    """Update a CRM profiling run log entry."""
    allowed = {"status", "agents_completed", "agents_failed", "duration_seconds", "error", "completed_at"}
    data = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not data:
        return
    sets = ", ".join(f"{k} = ?" for k in data)
    vals = list(data.values()) + [run_id]
    async with get_db() as db:
        await db.execute(f"UPDATE crm_profile_runs SET {sets} WHERE id = ?", vals)
        await db.commit()


async def get_crm_stats() -> dict:
    """Get CRM dashboard statistics."""
    async with get_db() as db:
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM crm_requests")
        total = (await cursor.fetchone())["cnt"]
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM crm_requests WHERE status = 'completed'")
        completed = (await cursor.fetchone())["cnt"]
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM crm_requests WHERE status = 'processing'")
        processing = (await cursor.fetchone())["cnt"]
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM crm_requests WHERE status = 'pending'")
        pending = (await cursor.fetchone())["cnt"]
        cursor = await db.execute(
            "SELECT AVG(overall_confidence) as avg_conf FROM crm_pic_profiles WHERE overall_confidence > 0"
        )
        avg_row = await cursor.fetchone()
        avg_confidence = avg_row["avg_conf"] if avg_row["avg_conf"] else 0.0
        return {
            "total_requests": total,
            "completed": completed,
            "processing": processing,
            "pending": pending,
            "avg_completion_confidence": round(avg_confidence, 2),
        }


# ── Email Blast Daily Quota ────────────────────────────────────────────────────

def _today_wib() -> str:
    """Return today's date string in WIB (UTC+7) format YYYY-MM-DD."""
    from datetime import datetime, timezone, timedelta
    wib = timezone(timedelta(hours=7))
    return datetime.now(wib).strftime("%Y-%m-%d")


async def get_email_blast_quota_info(limit: int) -> dict:
    """Return today's sent count and remaining quota."""
    today = _today_wib()
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT sent_count FROM email_blast_daily_quota WHERE quota_date = ?",
            (today,)
        )
        row = await cursor.fetchone()
        sent = row["sent_count"] if row else 0
        remaining = max(0, limit - sent)
        return {
            "date": today,
            "sent_today": sent,
            "daily_limit": limit,
            "remaining": remaining,
            "is_exhausted": remaining <= 0,
        }


async def increment_email_blast_quota(count: int = 1) -> int:
    """Increment today's sent count. Returns the new count."""
    today = _today_wib()
    async with get_db() as db:
        await db.execute(
            """INSERT INTO email_blast_daily_quota (quota_date, sent_count, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(quota_date) DO UPDATE SET
                   sent_count = sent_count + excluded.sent_count,
                   updated_at = datetime('now')""",
            (today, count)
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT sent_count FROM email_blast_daily_quota WHERE quota_date = ?",
            (today,)
        )
        row = await cursor.fetchone()
        return row["sent_count"] if row else count
