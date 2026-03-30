import os
import logging
import threading
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load .env first, then .env.production to override
load_dotenv()
load_dotenv(".env.production", override=True)

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Database
DATABASE_PATH = os.getenv("DATABASE_PATH", str(DATA_DIR / "getcontact.db"))

VISION_MODEL = "gpt-4o-mini"

# WhatsApp Service
WA_SERVICE_URL = os.getenv("WA_SERVICE_URL", "http://localhost:3100")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://localhost:8000/webhook/incoming")

TIMEZONE_WIB = "Asia/Jakarta"

# Follow-up timing (hours) — not dynamically configurable
FOLLOWUP_1_AFTER_HOURS = 24
FOLLOWUP_2_AFTER_HOURS = 48
MAX_FOLLOWUP_ATTEMPTS = 3

# Instagram settings — not dynamically configurable
IG_MAX_POSTS_PER_PROFILE = 200

# Instagram contact keywords (for filtering relevant posts)
CONTACT_KEYWORDS = [
    "narahubung", "contact person", "cp:", "cp :", "hubungi",
    "whatsapp", "wa:", "wa :", "info:", "info :",
    "pendaftaran", "kontak", "telepon", "telp", "phone",
    "nomor", "nomer",
]

# Instagram bio keywords (for verifying official accounts)
IG_BIO_KEYWORDS = [
    "resmi", "official", "universitas", "institut", "politeknik",
    "sekolah tinggi", "akademi", "kampus",
]

# PDDIKTI search prefixes
INSTITUTION_PREFIXES = [
    "Universitas", "Institut", "Politeknik", "Sekolah Tinggi",
    "STMIK", "STIE", "STKIP", "Akademi", "AMIK", "STIKES",
]

# Indonesian provinces for PDDIKTI search
PROVINCES = [
    "Aceh", "Sumatera Utara", "Sumatera Barat", "Riau",
    "Jambi", "Sumatera Selatan", "Bengkulu", "Lampung",
    "Kepulauan Bangka Belitung", "Kepulauan Riau",
    "DKI Jakarta", "Jawa Barat", "Jawa Tengah",
    "DI Yogyakarta", "Jawa Timur", "Banten",
    "Bali", "Nusa Tenggara Barat", "Nusa Tenggara Timur",
    "Kalimantan Barat", "Kalimantan Tengah", "Kalimantan Selatan",
    "Kalimantan Timur", "Kalimantan Utara",
    "Sulawesi Utara", "Sulawesi Tengah", "Sulawesi Selatan",
    "Sulawesi Tenggara", "Gorontalo", "Sulawesi Barat",
    "Maluku", "Maluku Utara", "Papua", "Papua Barat",
    "Papua Selatan", "Papua Tengah", "Papua Pegunungan", "Papua Barat Daya",
]

# Phone number regex patterns for Indonesian numbers
PHONE_PATTERNS = [
    r'(?:(?:\+62|62|0)[\s\-]?)'           # prefix
    r'(?:8\d{1,2})'                         # operator code
    r'[\s\-.]?'
    r'(?:\d{3,4})'
    r'[\s\-.]?'
    r'(?:\d{3,5})',
]

# Email Blast SMTP settings
SMTP_HOST = os.getenv("SMTP_HOST", "mail.asosiasi.ai")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "sekretariat@asosiasi.ai")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "SekertariatAInew343*")
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "true").lower() == "true"


# ---------------------------------------------------------------------------
# Model compatibility helpers
# ---------------------------------------------------------------------------
# Reasoning models (o-series, GPT-5) do NOT support temperature/top_p,
# use max_completion_tokens instead of max_tokens in Chat Completions API,
# and need a larger output-token budget because reasoning tokens count
# towards max_output_tokens / max_completion_tokens.

_NO_TEMPERATURE_PREFIXES = ("o1", "o3", "o4", "gpt-5")

# Minimum output-token budget for reasoning models.  Reasoning tokens are
# invisible but count towards the limit — if the budget is too small the
# model spends everything on reasoning and returns no visible message.
_REASONING_MIN_OUTPUT_TOKENS = 4096


def is_reasoning_model(model: str) -> bool:
    """Return True if *model* does not support temperature/top_p parameters.

    Covers o-series reasoning models and GPT-5 family.
    """
    m = model.lower().strip()
    return any(m.startswith(p) for p in _NO_TEMPERATURE_PREFIXES)


def _boost_for_reasoning(model: str, tokens: int) -> int:
    """Ensure reasoning models have enough output-token budget."""
    if is_reasoning_model(model):
        return max(tokens, _REASONING_MIN_OUTPUT_TOKENS)
    return tokens


def chat_kwargs(
    model: str,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict:
    """Build safe sampling kwargs for ``chat.completions.create()``."""
    params: dict = {}
    if not is_reasoning_model(model):
        if temperature is not None:
            params["temperature"] = temperature
    if max_tokens is not None:
        if is_reasoning_model(model):
            params["max_completion_tokens"] = _boost_for_reasoning(model, max_tokens)
        else:
            params["max_tokens"] = max_tokens
    return params


def responses_kwargs(
    model: str,
    *,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
) -> dict:
    """Build safe sampling kwargs for ``responses.create()``."""
    params: dict = {}
    if not is_reasoning_model(model):
        if temperature is not None:
            params["temperature"] = temperature
    if max_output_tokens is not None:
        params["max_output_tokens"] = _boost_for_reasoning(model, max_output_tokens)
    return params


# Logging
def setup_logger(name: str = "getcontact") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(handler)
    return logger


log = setup_logger()


# ---------------------------------------------------------------------------
# ConfigManager — dynamic, thread-safe configuration store
# ---------------------------------------------------------------------------

from orchestrator.config_registry import CONFIG_DEFINITIONS_MAP, ConfigType, ConfigDef  # noqa: E402


def _parse_value(raw: str, cfg_type: ConfigType) -> Any:
    """Convert a string value to the correct Python type."""
    if cfg_type == ConfigType.INT:
        return int(raw)
    if cfg_type == ConfigType.FLOAT:
        return float(raw)
    if cfg_type == ConfigType.BOOL:
        return raw.lower() in ("true", "1", "yes")
    return raw


class ConfigManager:
    """Thread-safe dynamic configuration store.

    Precedence: DB value > .env value > registry default.

    All modules importing ``cfg`` share the same object reference,
    so ``cfg.SETTING`` always returns the latest value.
    """

    _INTERNAL = {"_store", "_lock"}

    def __init__(self) -> None:
        object.__setattr__(self, "_store", {})
        object.__setattr__(self, "_lock", threading.Lock())

    # -- attribute access ------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        store: dict = object.__getattribute__(self, "_store")
        lock: threading.Lock = object.__getattribute__(self, "_lock")
        with lock:
            if name in store:
                return store[name]
        raise AttributeError(f"ConfigManager has no setting '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        if name in self._INTERNAL:
            object.__setattr__(self, name, value)
            return
        with self._lock:
            self._store[name] = value

    # -- initialisation -------------------------------------------------------

    def init_from_env(self) -> None:
        """Populate store from .env / registry defaults (called at import time)."""
        with self._lock:
            for key, defn in CONFIG_DEFINITIONS_MAP.items():
                env_val = os.getenv(key)
                if env_val is not None:
                    self._store[key] = _parse_value(env_val, defn.type)
                else:
                    self._store[key] = defn.default

    async def init_from_db(self) -> None:
        """Override store with values persisted in the DB config table.

        Must be called after ``init_db()``.
        Skips any key marked ``env_only=True`` — those are locked to env vars only.
        """
        from orchestrator.db import get_all_config

        rows = await get_all_config()
        loaded = 0
        with self._lock:
            for key, raw_value in rows.items():
                defn = CONFIG_DEFINITIONS_MAP.get(key)
                if defn is None:
                    continue
                if defn.env_only:
                    log.info("ConfigManager: skipping DB override for env_only key %s (using env value)", key)
                    continue
                try:
                    self._store[key] = _parse_value(raw_value, defn.type)
                    loaded += 1
                except (ValueError, TypeError):
                    log.warning("Invalid DB config value for %s: %r", key, raw_value)

        log.info("ConfigManager: loaded %d overrides from DB (%d skipped env_only)", loaded, len(rows) - loaded)

    # -- get / set / get_all ---------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._store.get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = value

    def get_all(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._store)


cfg = ConfigManager()
cfg.init_from_env()

# ---------------------------------------------------------------------------
# Backward-compat module-level aliases (snapshot at import time).
# Modules migrated to ``cfg.X`` will always get the latest value.
# These aliases exist only for files that still do
# ``from orchestrator.config import OPENAI_API_KEY`` etc.
# NOTE: because these are snapshots, the *migrated* ``cfg.X`` path
# is preferred for any code that should react to runtime changes.
# ---------------------------------------------------------------------------
OPENAI_API_KEY = cfg.OPENAI_API_KEY
SERPER_API_KEY = cfg.SERPER_API_KEY
CHAT_MODEL = cfg.AGENT_MODEL
MAX_DAILY_CONVERSATIONS = cfg.MAX_DAILY_CONVERSATIONS
MIN_MESSAGE_GAP_SECONDS = cfg.MIN_MESSAGE_GAP_SECONDS
MAX_IG_PROFILES_PER_DAY = cfg.MAX_IG_PROFILES_PER_DAY
IG_REQUEST_DELAY_SECONDS = cfg.IG_REQUEST_DELAY_SECONDS
OUTREACH_START_HOUR = cfg.OUTREACH_START_HOUR
OUTREACH_END_HOUR = cfg.OUTREACH_END_HOUR
USE_AGENTIC_REPLIES = cfg.USE_AGENTIC_REPLIES
USE_AGENTIC_INITIAL = cfg.USE_AGENTIC_INITIAL
USE_AGENTIC_FOLLOWUPS = cfg.USE_AGENTIC_FOLLOWUPS
LEARNING_ENABLED = cfg.LEARNING_ENABLED
AGENT_MODEL = cfg.AGENT_MODEL
AGENT_TEMPERATURE = cfg.AGENT_TEMPERATURE
AGENT_MAX_TOKENS = cfg.AGENT_MAX_TOKENS
AGENT_MAX_TOOL_ITERATIONS = cfg.AGENT_MAX_TOOL_ITERATIONS
MAX_AI_CONCURRENT = cfg.MAX_AI_CONCURRENT
SEND_INTERVAL_MS = cfg.SEND_INTERVAL_MS
REFLECTION_INTERVAL_HOURS = int(os.getenv("REFLECTION_INTERVAL_HOURS", "6"))
MAX_LESSONS_IN_PROMPT = int(os.getenv("MAX_LESSONS_IN_PROMPT", "5"))
MAX_KNOWLEDGE_IN_PROMPT = int(os.getenv("MAX_KNOWLEDGE_IN_PROMPT", "5"))
MAX_KNOWLEDGE_ITEM_LENGTH = int(os.getenv("MAX_KNOWLEDGE_ITEM_LENGTH", "300"))


# Pause state (thread-safe)
_is_paused = False
_pause_lock = threading.Lock()


def is_paused() -> bool:
    with _pause_lock:
        return _is_paused


def set_paused(val: bool) -> None:
    global _is_paused
    with _pause_lock:
        _is_paused = val
