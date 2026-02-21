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
        label="Serper API Key",
        description="API key for Serper.dev Google Search.",
        sensitive=True,
    ),
    ConfigDef(
        key="IG_SESSION_ID",
        type=ConfigType.STRING, default="", group=ConfigGroup.CREDENTIALS,
        label="IG Session ID",
        description="Instagram Web API session cookie for scraping.",
        sensitive=True,
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
        type=ConfigType.INT, default=7, group=ConfigGroup.INSTAGRAM,
        label="IG Request Delay (s)",
        description="Seconds between Instagram API requests.",
        min_value=1, max_value=60,
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
        type=ConfigType.INT, default=5, group=ConfigGroup.AI_AGENT,
        label="Agent Max Tool Iterations",
        description="Max ReAct loop iterations before forcing a response.",
        min_value=1, max_value=20,
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
]

CONFIG_DEFINITIONS_MAP: dict[str, ConfigDef] = {d.key: d for d in CONFIG_DEFINITIONS}
