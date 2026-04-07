"""
Registry of all dynamically configurable settings.

Each setting has a type, default value, group, label, description,
and optional min/max constraints for numeric types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ConfigType(str, Enum):
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    STRING = "string"


class ConfigGroup(str, Enum):
    RATE_LIMITING = "Rate Limiting"
    OUTREACH = "Outreach"
    INSTAGRAM = "Instagram"
    AI_AGENT = "AI Agent"
    MESSAGE_QUEUE = "Message Queue"
    CREDENTIALS = "Credentials"
    AUDIENSI = "Audiensi"
    KNOWLEDGE_BASE = "Knowledge Base"
    PLAYWRIGHT = "Playwright Browser"
    DMS_INTEGRATION = "DMS Integration"
    GENERAL = "General"


@dataclass(frozen=True)
class ConfigDef:
    key: str
    type: ConfigType
    default: Any
    group: ConfigGroup
    label: str
    description: str
    min_value: float | None = None
    max_value: float | None = None
    sensitive: bool = False  # if True, value is masked in GET response
    env_only: bool = False  # if True, cannot be changed via DB or FE API — env var only
    choices: list[str] | None = None  # if set, rendered as static dropdown in UI
    model_picker: str | None = None  # if set, rendered as dynamic model dropdown: "openai" | "gemini" | "all"


CONFIG_DEFINITIONS: list[ConfigDef] = [
    # --- Credentials (sensitive) ---
    ConfigDef(
        key="OPENAI_API_KEY",
        type=ConfigType.STRING, default="", group=ConfigGroup.CREDENTIALS,
        label="OpenAI API Key",
        description="API key for OpenAI GPT calls.",
        sensitive=True,
    ),
    ConfigDef(
        key="SERPER_API_KEY",
        type=ConfigType.STRING, default="", group=ConfigGroup.CREDENTIALS,
        label="Serper API Key (Legacy)",
        description=(
            "Legacy: API key for Serper.dev Google Search. "
            "DuckDuckGo is now used as the primary search engine (free, no key needed). "
            "Leave empty unless you want to use Serper as an additional fallback."
        ),
        sensitive=True,
    ),
    ConfigDef(
        key="IG_SESSION_ID",
        type=ConfigType.STRING, default="", group=ConfigGroup.CREDENTIALS,
        label="IG Session ID(s)",
        description=(
            "Instagram session cookie(s) for scraping. "
            "Supports multiple sessions separated by commas for automatic rotation — "
            "when one session gets suspended, the next one is used automatically. "
            "Get from browser: F12 → Application → Cookies → instagram.com → sessionid"
        ),
        sensitive=True,
    ),
    # --- Chatbot Toggles ---
    ConfigDef(
        key="CHATBOT_ENABLED",
        type=ConfigType.BOOL, default=True, group=ConfigGroup.OUTREACH,
        label="Contact Finder Chatbot",
        description="Enable/disable the contact finder chatbot (outreach, replies, follow-ups).",
    ),
    # --- Rate Limiting ---
    ConfigDef(
        key="MAX_DAILY_CONVERSATIONS",
        type=ConfigType.INT, default=20, group=ConfigGroup.RATE_LIMITING,
        label="Max Daily Conversations",
        description="Maximum new conversations started per day.",
        min_value=1, max_value=500,
    ),
    ConfigDef(
        key="MIN_MESSAGE_GAP_SECONDS",
        type=ConfigType.INT, default=300, group=ConfigGroup.RATE_LIMITING,
        label="Min Message Gap (s)",
        description="Minimum seconds between outreach messages.",
        min_value=10, max_value=3600,
    ),
    # --- Instagram ---
    ConfigDef(
        key="MAX_IG_PROFILES_PER_DAY",
        type=ConfigType.INT, default=200, group=ConfigGroup.INSTAGRAM,
        label="Max IG Profiles / Day",
        description="Maximum Instagram profiles scraped per day.",
        min_value=1, max_value=1000,
    ),
    ConfigDef(
        key="IG_REQUEST_DELAY_SECONDS",
        type=ConfigType.INT, default=30, group=ConfigGroup.INSTAGRAM,
        label="IG API Request Delay (s)",
        description="Seconds between direct IG API requests (Tier 1). Increased to reduce ban risk.",
        min_value=10, max_value=120,
    ),
    # --- Playwright Browser (Tier 0 — primary IG scraper) ---
    ConfigDef(
        key="PW_HEADLESS",
        type=ConfigType.BOOL, default=True, group=ConfigGroup.PLAYWRIGHT,
        label="Headless Mode",
        description="Run Playwright browser without visible window (recommended for production).",
    ),
    ConfigDef(
        key="PW_MIN_DELAY_SECONDS",
        type=ConfigType.INT, default=8, group=ConfigGroup.PLAYWRIGHT,
        label="Min Delay (s)",
        description="Minimum delay between Playwright actions (human-like behavior).",
        min_value=3, max_value=60,
    ),
    ConfigDef(
        key="PW_MAX_DELAY_SECONDS",
        type=ConfigType.INT, default=20, group=ConfigGroup.PLAYWRIGHT,
        label="Max Delay (s)",
        description="Maximum delay between Playwright actions.",
        min_value=5, max_value=120,
    ),
    ConfigDef(
        key="PW_PROFILES_PER_SESSION",
        type=ConfigType.INT, default=15, group=ConfigGroup.PLAYWRIGHT,
        label="Profiles per Session",
        description="Max profiles to scrape before restarting browser (prevents detection).",
        min_value=3, max_value=50,
    ),
    ConfigDef(
        key="PW_DAILY_LIMIT",
        type=ConfigType.INT, default=100, group=ConfigGroup.PLAYWRIGHT,
        label="Daily Limit",
        description="Max profiles scraped per day via Playwright.",
        min_value=10, max_value=500,
    ),
    ConfigDef(
        key="PW_ACCOUNT_COOLDOWN_MINUTES",
        type=ConfigType.INT, default=30, group=ConfigGroup.PLAYWRIGHT,
        label="Account Cooldown (min)",
        description="Minutes to cool down a rate-limited account before retrying.",
        min_value=5, max_value=240,
    ),
    ConfigDef(
        key="INSTALOADER_ENABLED",
        type=ConfigType.BOOL, default=True, group=ConfigGroup.PLAYWRIGHT,
        label="Instaloader Enabled",
        description="Enable Instaloader (no-session, free) as fallback for Instagram post scraping when Playwright returns alt-text captions.",
    ),
    ConfigDef(
        key="INSTALOADER_REQUEST_DELAY",
        type=ConfigType.FLOAT, default=2.0, group=ConfigGroup.PLAYWRIGHT,
        label="Instaloader Request Delay (s)",
        description="Seconds to wait between Instaloader post fetches to avoid IP bans. Default: 2.0",
        min_value=0.5, max_value=30.0,
    ),
    # --- Outreach ---
    ConfigDef(
        key="OUTREACH_START_HOUR",
        type=ConfigType.INT, default=7, group=ConfigGroup.OUTREACH,
        label="Outreach Start Hour",
        description="Start of outreach window (WIB, 0-23).",
        min_value=0, max_value=23,
    ),
    ConfigDef(
        key="OUTREACH_END_HOUR",
        type=ConfigType.INT, default=22, group=ConfigGroup.OUTREACH,
        label="Outreach End Hour",
        description="End of outreach window (WIB, 0-23).",
        min_value=1, max_value=24,
    ),
    # --- AI Agent ---
    ConfigDef(
        key="USE_AGENTIC_REPLIES",
        type=ConfigType.BOOL, default=True, group=ConfigGroup.AI_AGENT,
        label="Agentic Replies",
        description="Use ReAct agent for processing incoming replies.",
    ),
    ConfigDef(
        key="USE_AGENTIC_INITIAL",
        type=ConfigType.BOOL, default=False, group=ConfigGroup.AI_AGENT,
        label="Agentic Initial Messages",
        description="Use ReAct agent for generating initial outreach messages.",
    ),
    ConfigDef(
        key="USE_AGENTIC_FOLLOWUPS",
        type=ConfigType.BOOL, default=True, group=ConfigGroup.AI_AGENT,
        label="Agentic Follow-ups",
        description="Use ReAct agent for generating follow-up messages.",
    ),
    ConfigDef(
        key="LEARNING_ENABLED",
        type=ConfigType.BOOL, default=True, group=ConfigGroup.AI_AGENT,
        label="Learning Enabled",
        description="Enable post-conversation analysis and lesson extraction.",
    ),
    ConfigDef(
        key="AGENT_MODEL",
        type=ConfigType.STRING, default="gpt-4o-mini", group=ConfigGroup.AI_AGENT,
        label="Agent Model",
        description="OpenAI model used by the ReAct agent.",
    ),
    ConfigDef(
        key="AGENT_TEMPERATURE",
        type=ConfigType.FLOAT, default=0.4, group=ConfigGroup.AI_AGENT,
        label="Agent Temperature",
        description="Temperature for agent GPT calls.",
        min_value=0.0, max_value=2.0,
    ),
    ConfigDef(
        key="AGENT_MAX_TOKENS",
        type=ConfigType.INT, default=500, group=ConfigGroup.AI_AGENT,
        label="Agent Max Tokens",
        description="Max tokens per agent GPT response.",
        min_value=100, max_value=4000,
    ),
    ConfigDef(
        key="AGENT_MAX_TOOL_ITERATIONS",
        type=ConfigType.INT, default=10, group=ConfigGroup.AI_AGENT,
        label="Agent Max Tool Iterations",
        description="Max ReAct loop iterations before forcing a response.",
        min_value=1, max_value=20,
    ),
    ConfigDef(
        key="AGENT_PLANNING_ENABLED",
        type=ConfigType.BOOL, default=True, group=ConfigGroup.AI_AGENT,
        label="Agent Planning Enabled",
        description="Pre-compute a strategy plan before the ReAct loop (uses gpt-4o-mini).",
    ),
    ConfigDef(
        key="MARKETING_GEMINI_ENABLED",
        type=ConfigType.BOOL, default=True, group=ConfigGroup.AI_AGENT,
        label="Marketing Gemini Grounding",
        description="Enable Gemini with Google Search grounding as a final gap-fill stage in the marketing contact discovery pipeline.",
    ),
    ConfigDef(
        key="MARKETING_ORCHESTRATOR_MODEL",
        type=ConfigType.STRING, default="gemini-3.1-pro-preview", group=ConfigGroup.AI_AGENT,
        label="Marketing Orchestrator Model",
        description="Model for the marketing discovery orchestrator agent. Prefix 'gemini-' uses Gemini API (recommended), 'gpt-' uses OpenAI Responses API.",
        model_picker="all",
    ),
    ConfigDef(
        key="MARKETING_SUB_AGENT_MODEL",
        type=ConfigType.STRING, default="gpt-4o-mini", group=ConfigGroup.AI_AGENT,
        label="Marketing Sub-Agent Model",
        description="OpenAI model for marketing sub-agents (web search, instagram, etc.).",
        model_picker="openai",
    ),
    ConfigDef(
        key="MARKETING_AGENT_MAX_TOOL_ITERATIONS",
        type=ConfigType.INT, default=15, group=ConfigGroup.AI_AGENT,
        label="Marketing Agent Max Tool Iterations",
        description="Max ReAct loop iterations for the marketing orchestrator agent before forcing termination.",
        min_value=1, max_value=50,
    ),
    # --- Message Queue ---
    ConfigDef(
        key="MAX_AI_CONCURRENT",
        type=ConfigType.INT, default=3, group=ConfigGroup.MESSAGE_QUEUE,
        label="Max AI Concurrent",
        description="Max concurrent AI processing tasks. Requires restart to take effect.",
        min_value=1, max_value=20,
    ),
    ConfigDef(
        key="SEND_INTERVAL_MS",
        type=ConfigType.INT, default=3000, group=ConfigGroup.MESSAGE_QUEUE,
        label="Send Interval (ms)",
        description="Milliseconds between serial WA message sends.",
        min_value=500, max_value=30000,
    ),
    # --- Audiensi ---
    ConfigDef(
        key="AUDIENSI_ENABLED",
        type=ConfigType.BOOL, default=False, group=ConfigGroup.AUDIENSI,
        label="Audiensi Enabled",
        description="Enable audiensi chatbot (Phase 2) features.",
    ),
    ConfigDef(
        key="AUDIENSI_AUTO_APPROVE",
        type=ConfigType.BOOL, default=False, group=ConfigGroup.AUDIENSI,
        label="Auto-Approve Audiensi",
        description="Automatically approve and send audiensi messages when a number is obtained (skip manual review).",
    ),
    ConfigDef(
        key="AUTO_APPROVE_AUDIENSI",
        type=ConfigType.BOOL, default=False, group=ConfigGroup.AUDIENSI,
        label="Auto-Approve Queued Audiensi",
        description=(
            "Automatically approve QUEUED audiensi records after a delay. "
            "Requires AUTO_APPROVE_DELAY_MINUTES to be set. "
            "Disabled by default — requires explicit operator opt-in."
        ),
    ),
    ConfigDef(
        key="AUTO_APPROVE_DELAY_MINUTES",
        type=ConfigType.INT, default=60, group=ConfigGroup.AUDIENSI,
        label="Auto-Approve Delay (minutes)",
        description="Minutes to wait before auto-approving a QUEUED audiensi record.",
        min_value=5, max_value=1440,
    ),
    ConfigDef(
        key="AUDIENSI_FOLLOWUP_AFTER_HOURS",
        type=ConfigType.INT, default=48, group=ConfigGroup.AUDIENSI,
        label="Audiensi Followup After (hours)",
        description="Hours to wait before sending audiensi follow-up.",
        min_value=1, max_value=168,
    ),
    ConfigDef(
        key="AUDIENSI_MAX_FOLLOWUPS",
        type=ConfigType.INT, default=3, group=ConfigGroup.AUDIENSI,
        label="Audiensi Max Follow-ups",
        description="Maximum follow-up attempts for audiensi conversations.",
        min_value=1, max_value=10,
    ),
    ConfigDef(
        key="AUDIENSI_ZOOM_LINK_TEMPLATE",
        type=ConfigType.STRING, default="", group=ConfigGroup.AUDIENSI,
        label="Zoom Link Template",
        description="Default Zoom meeting link (placeholder for integration).",
    ),
    ConfigDef(
        key="AUDIENSI_PDF_TEMPLATE_PATH",
        type=ConfigType.STRING, default="", group=ConfigGroup.AUDIENSI,
        label="PDF Template Path",
        description="Custom path to audiensi surat undangan .docx template.",
    ),
    ConfigDef(
        key="API_LOG_RETENTION_DAYS",
        type=ConfigType.INT, default=7, group=ConfigGroup.AI_AGENT,
        label="API Log Retention (days)",
        description="Hapus API call logs yang lebih lama dari N hari.",
        min_value=1, max_value=90,
    ),
    # --- Knowledge Base ---
    ConfigDef(
        key="AGENT_CUSTOM_INSTRUCTIONS",
        type=ConfigType.STRING, default="", group=ConfigGroup.KNOWLEDGE_BASE,
        label="Contact Finder Custom Instructions",
        description="Instruksi/pengetahuan tambahan untuk chatbot contact finder. Di-inject ke system prompt.",
    ),
    ConfigDef(
        key="AUDIENSI_CUSTOM_INSTRUCTIONS",
        type=ConfigType.STRING, default="", group=ConfigGroup.KNOWLEDGE_BASE,
        label="Audiensi Custom Instructions",
        description="Instruksi/pengetahuan tambahan untuk chatbot audiensi. Di-inject ke system prompt.",
    ),
    # --- Scraping Fallback APIs ---
    ConfigDef(
        key="BRAVE_API_KEY",
        type=ConfigType.STRING, default="", group=ConfigGroup.CREDENTIALS,
        label="Brave Search API Key",
        description=(
            "API key for Brave Web Search. Better quality than DDG for Indonesian content. "
            "Get from: https://brave.com/search/api/"
        ),
        sensitive=True,
    ),
    ConfigDef(
        key="APIFY_API_KEY",
        type=ConfigType.STRING, default="", group=ConfigGroup.CREDENTIALS,
        label="Apify API Key",
        description=(
            "API key for Apify.com Instagram Scraper (fallback when IG sessions fail). "
            "Get from: https://console.apify.com/account/integrations"
        ),
        sensitive=True,
    ),
    ConfigDef(
        key="SCRAPINGBOT_USERNAME",
        type=ConfigType.STRING, default="", group=ConfigGroup.CREDENTIALS,
        label="ScrapingBot Username",
        description=(
            "Username for Scraping-Bot.io (Tier 3 fallback). "
            "Get from: https://www.scraping-bot.io/dashboard/"
        ),
        sensitive=True,
    ),
    ConfigDef(
        key="SCRAPINGBOT_API_KEY",
        type=ConfigType.STRING, default="", group=ConfigGroup.CREDENTIALS,
        label="ScrapingBot API Key",
        description=(
            "API key for Scraping-Bot.io Social Media API (Tier 3 fallback). "
            "Get from: https://www.scraping-bot.io/dashboard/"
        ),
        sensitive=True,
    ),
    # --- Agent Rolling Position ---
    ConfigDef(
        key="AGENT_LAST_PROCESSED_UNIV_ID",
        type=ConfigType.INT, default=0, group=ConfigGroup.INSTAGRAM,
        label="Last Processed University ID",
        description="ID universitas terakhir yang diproses oleh agents (untuk rolling mechanism).",
        min_value=0,
    ),
    ConfigDef(
        key="TARGET_POSTS_PER_UNIVERSITY",
        type=ConfigType.INT, default=100, group=ConfigGroup.INSTAGRAM,
        label="Target Posts per University",
        description="Target jumlah posts per universitas (dari gabungan IG utama + related IGs).",
        min_value=10, max_value=500,
    ),
    # --- DMS Integration (MySQL) ---
    ConfigDef(
        key="DMS_MYSQL_HOST",
        type=ConfigType.STRING, default="", group=ConfigGroup.DMS_INTEGRATION,
        label="DMS MySQL Host",
        description="Hostname/IP database DMS (dev staging atau production). Kosong = disabled. ENV ONLY.",
        sensitive=True,
        env_only=True,
    ),
    ConfigDef(
        key="DMS_MYSQL_PORT",
        type=ConfigType.INT, default=3306, group=ConfigGroup.DMS_INTEGRATION,
        label="DMS MySQL Port",
        description="Port database DMS MySQL. ENV ONLY.",
        min_value=1, max_value=65535,
        sensitive=True,
        env_only=True,
    ),
    ConfigDef(
        key="DMS_MYSQL_USER",
        type=ConfigType.STRING, default="", group=ConfigGroup.DMS_INTEGRATION,
        label="DMS MySQL User",
        description="Username untuk koneksi database DMS. ENV ONLY.",
        sensitive=True,
        env_only=True,
    ),
    ConfigDef(
        key="DMS_MYSQL_PASSWORD",
        type=ConfigType.STRING, default="", group=ConfigGroup.DMS_INTEGRATION,
        label="DMS MySQL Password",
        description="Password untuk koneksi database DMS. ENV ONLY.",
        sensitive=True,
        env_only=True,
    ),
    ConfigDef(
        key="DMS_MYSQL_DATABASE",
        type=ConfigType.STRING, default="", group=ConfigGroup.DMS_INTEGRATION,
        label="DMS MySQL Database",
        description="Nama database DMS (e.g. dev_staging_dmsedu). ENV ONLY.",
        sensitive=True,
        env_only=True,
    ),
    ConfigDef(
        key="DMS_SYNC_ENABLED",
        type=ConfigType.BOOL, default=False, group=ConfigGroup.DMS_INTEGRATION,
        label="Aktifkan DMS Sync",
        description="Aktifkan sinkronisasi otomatis dengan database DMS (read jadwal audiensi, sync kontak).",
    ),
    ConfigDef(
        key="DMS_SYNC_INTERVAL_MINUTES",
        type=ConfigType.INT, default=30, group=ConfigGroup.DMS_INTEGRATION,
        label="DMS Sync Interval (menit)",
        description="Interval sinkronisasi data dari DMS MySQL ke sistem GetContact.",
        min_value=5, max_value=1440,
    ),
    ConfigDef(
        key="AUTH_COOKIE_NAME",
        type=ConfigType.STRING, default="dms_marketing_session", group=ConfigGroup.DMS_INTEGRATION,
        label="Auth Cookie Name",
        description="Nama cookie session untuk login dashboard. ENV ONLY.",
        env_only=True,
    ),
    ConfigDef(
        key="AUTH_SESSION_TTL_HOURS",
        type=ConfigType.INT, default=12, group=ConfigGroup.DMS_INTEGRATION,
        label="Auth Session TTL (jam)",
        description="Masa aktif session login dashboard dalam jam. ENV ONLY.",
        min_value=1, max_value=168,
        env_only=True,
    ),
    ConfigDef(
        key="AUTH_COOKIE_SECURE",
        type=ConfigType.BOOL, default=False, group=ConfigGroup.DMS_INTEGRATION,
        label="Auth Cookie Secure",
        description="Gunakan cookie secure (HTTPS only) untuk login dashboard. ENV ONLY.",
        env_only=True,
    ),
    ConfigDef(
        key="AUTH_DEFAULT_PASSWORD",
        type=ConfigType.STRING, default="", group=ConfigGroup.DMS_INTEGRATION,
        label="Auth Default Password",
        description="Password default untuk login dashboard semua user DMS aktif. ENV ONLY.",
        env_only=True,
    ),
    ConfigDef(
        key="AUTH_DEFAULT_ROLE",
        type=ConfigType.STRING, default="viewer", group=ConfigGroup.DMS_INTEGRATION,
        label="Auth Default Role",
        description="Role lokal otomatis untuk user DMS aktif yang login memakai password default. ENV ONLY.",
        env_only=True,
    ),
    ConfigDef(
        key="DMS_CONTACT_SYNC_ENABLED",
        type=ConfigType.BOOL, default=False, group=ConfigGroup.DMS_INTEGRATION,
        label="Sync Kontak ke DMS",
        description="Otomatis sinkronkan kontak yang ditemukan oleh GetContact ke tabel kontak_auto di DMS.",
    ),
    ConfigDef(
        key="DMS_REMINDER_ENABLED",
        type=ConfigType.BOOL, default=False, group=ConfigGroup.DMS_INTEGRATION,
        label="WhatsApp Reminder Audiensi",
        description="Kirim reminder WhatsApp otomatis untuk jadwal audiensi dari DMS.",
    ),
    ConfigDef(
        key="DMS_REMINDER_HOURS_BEFORE",
        type=ConfigType.INT, default=24, group=ConfigGroup.DMS_INTEGRATION,
        label="Reminder Hours Before",
        description="Kirim reminder H-berapa jam sebelum jadwal audiensi.",
        min_value=1, max_value=72,
    ),

    # --- Audiensi Research (Gemini AI) ---
    ConfigDef(
        key="GEMINI_API_KEY",
        type=ConfigType.STRING, default="", group=ConfigGroup.DMS_INTEGRATION,
        label="Gemini API Key",
        description="API key untuk Google Gemini AI (digunakan untuk riset latar belakang audiensi).",
        sensitive=True,
    ),
    ConfigDef(
        key="DMS_RESEARCH_ENABLED",
        type=ConfigType.BOOL, default=False, group=ConfigGroup.DMS_INTEGRATION,
        label="Riset Audiensi Otomatis",
        description="Aktifkan riset otomatis H-1 audiensi menggunakan Gemini AI dengan Google Search.",
    ),
    ConfigDef(
        key="DMS_RESEARCH_NOTIFY_PHONES",
        type=ConfigType.STRING, default="", group=ConfigGroup.DMS_INTEGRATION,
        label="Nomor WA Notifikasi Riset",
        description="Nomor WhatsApp tujuan notifikasi hasil riset (pisahkan dengan koma). Contoh: 6281234567890,6289876543210",
    ),
    ConfigDef(
        key="DMS_RESEARCH_HOUR",
        type=ConfigType.INT, default=18, group=ConfigGroup.DMS_INTEGRATION,
        label="Jam Riset Audiensi (WIB)",
        description="Jam berapa (WIB) riset H-1 audiensi dijalankan setiap hari.",
        min_value=0, max_value=23,
    ),
    ConfigDef(
        key="RESEARCH_USE_MULTI_AGENT",
        type=ConfigType.BOOL, default=False, group=ConfigGroup.DMS_INTEGRATION,
        label="Multi-Agent Research",
        description=(
            "Gunakan pipeline multi-agent (LangGraph) untuk riset audiensi. "
            "Setiap pertanyaan didedikasikan ke 1 agent + reviewer. "
            "Jika false, gunakan single-prompt legacy."
        ),
    ),
    # Email Blast SMTP Settings
    ConfigDef(
        key="SMTP_HOST", type=ConfigType.STRING, default="mail.asosiasi.ai",
        group=ConfigGroup.GENERAL, label="SMTP Host",
        description="SMTP server hostname for email blast"
    ),
    ConfigDef(
        key="SMTP_PORT", type=ConfigType.INT, default=465,
        group=ConfigGroup.GENERAL, label="SMTP Port",
        description="SMTP server port (465 for SSL, 587 for TLS)"
    ),
    ConfigDef(
        key="SMTP_USERNAME", type=ConfigType.STRING, default="sekretariat@asosiasi.ai",
        group=ConfigGroup.GENERAL, label="SMTP Username",
        description="SMTP authentication username"
    ),
    ConfigDef(
        key="SMTP_PASSWORD", type=ConfigType.STRING, default="SekertariatAInew343*",
        group=ConfigGroup.GENERAL, label="SMTP Password",
        description="SMTP authentication password"
    ),
    ConfigDef(
        key="SMTP_USE_SSL", type=ConfigType.BOOL, default=True,
        group=ConfigGroup.GENERAL, label="SMTP Use SSL",
        description="Use SSL for SMTP connection (default: true for port 465)"
    ),
    ConfigDef(
        key="SMTP_ACCOUNTS", type=ConfigType.STRING, default="",
        group=ConfigGroup.GENERAL, label="SMTP Accounts (JSON array)",
        description=(
            "JSON array of SMTP accounts for rotation. Format: "
            "[{\"host\":\"mail.asosiasi.ai\",\"port\":465,\"user\":\"acc1@asosiasi.ai\","
            "\"password\":\"xxx\",\"use_ssl\":true}, ...]. "
            "Leave empty to use single account (SMTP_HOST/USERNAME/etc)."
        ),
        sensitive=True,
        env_only=True,
    ),
    ConfigDef(
        key="ROTATE_AFTER_N_EMAILS", type=ConfigType.INT, default=50,
        group=ConfigGroup.GENERAL, label="Rotate SMTP After N Emails",
        description="Switch to next SMTP account after sending N emails (per account). Prevents rate-limit bans."
    ),
    ConfigDef(
        key="SMTP_ACCOUNT_MIN_COOLDOWN_SECONDS", type=ConfigType.INT, default=60,
        group=ConfigGroup.GENERAL, label="SMTP Account Cooldown Seconds",
        description="Minimum cooldown between sends on the same SMTP mailbox. Helps avoid rapid-fire patterns.",
        min_value=0, max_value=3600,
    ),
    ConfigDef(
        key="SMTP_ACCOUNT_DAILY_LIMIT", type=ConfigType.INT, default=40,
        group=ConfigGroup.GENERAL, label="SMTP Account Daily Limit",
        description="Maximum emails per SMTP mailbox per day. 0 = unlimited.",
        min_value=0, max_value=10000,
    ),
    ConfigDef(
        key="EMAIL_BLAST_DELAY_JITTER_MS", type=ConfigType.INT, default=5000,
        group=ConfigGroup.GENERAL, label="Email Blast Delay Jitter (ms)",
        description="Random extra delay added after each email send to avoid perfectly uniform timing.",
        min_value=0, max_value=600000,
    ),
    ConfigDef(
        key="VALIDATE_EMAIL_BEFORE_SEND", type=ConfigType.BOOL, default=True,
        group=ConfigGroup.GENERAL, label="Validate Emails Before Sending",
        description="Check email syntax and MX record before sending. Invalid emails are skipped (not failed). Reduces bounce rate."
    ),
    # Email Blast IMAP Settings (for receiving replies)
    ConfigDef(
        key="IMAP_HOST", type=ConfigType.STRING, default="mail.asosiasi.ai",
        group=ConfigGroup.GENERAL, label="IMAP Host",
        description="IMAP server hostname for receiving email replies"
    ),
    ConfigDef(
        key="IMAP_PORT", type=ConfigType.INT, default=993,
        group=ConfigGroup.GENERAL, label="IMAP Port",
        description="IMAP server port (993 for SSL, 143 for TLS)"
    ),
    ConfigDef(
        key="IMAP_USERNAME", type=ConfigType.STRING, default="sekretariat@asosiasi.ai",
        group=ConfigGroup.GENERAL, label="IMAP Username",
        description="IMAP authentication username"
    ),
    ConfigDef(
        key="IMAP_PASSWORD", type=ConfigType.STRING, default="SekertariatAInew343*",
        group=ConfigGroup.GENERAL, label="IMAP Password",
        description="IMAP authentication password"
    ),
    ConfigDef(
        key="IMAP_USE_SSL", type=ConfigType.BOOL, default=True,
        group=ConfigGroup.GENERAL, label="IMAP Use SSL",
        description="Use SSL for IMAP connection (default: true for port 993)"
    ),
    # Email Blast
    ConfigDef(
        key="EMAIL_BLAST_DAILY_LIMIT", type=ConfigType.INT, default=200,
        group=ConfigGroup.GENERAL, label="Email Blast Daily Limit",
        description="Maximum emails to send per day (WIB). 0 = unlimited.",
        min_value=0, max_value=10000,
    ),
]

CONFIG_DEFINITIONS_MAP: dict[str, ConfigDef] = {d.key: d for d in CONFIG_DEFINITIONS}
