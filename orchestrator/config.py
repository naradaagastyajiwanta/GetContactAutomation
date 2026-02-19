import os
import logging
import threading
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Database
DATABASE_PATH = os.getenv("DATABASE_PATH", str(DATA_DIR / "getcontact.db"))

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
VISION_MODEL = "gpt-4o-mini"
CHAT_MODEL = "gpt-4o-mini"

# Serper.dev (Google Search)
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")

# Instagram
MAX_IG_PROFILES_PER_DAY = int(os.getenv("MAX_IG_PROFILES_PER_DAY", "200"))
IG_REQUEST_DELAY_SECONDS = int(os.getenv("IG_REQUEST_DELAY_SECONDS", "7"))
IG_MAX_POSTS_PER_PROFILE = 20

# WhatsApp Service
WA_SERVICE_URL = os.getenv("WA_SERVICE_URL", "http://localhost:3100")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://localhost:8000/webhook/incoming")

# Rate Limiting
MAX_DAILY_CONVERSATIONS = int(os.getenv("MAX_DAILY_CONVERSATIONS", "20"))
MIN_MESSAGE_GAP_SECONDS = int(os.getenv("MIN_MESSAGE_GAP_SECONDS", "300"))

# Outreach Hours (WIB = UTC+7)
OUTREACH_START_HOUR = int(os.getenv("OUTREACH_START_HOUR", "7"))
OUTREACH_END_HOUR = int(os.getenv("OUTREACH_END_HOUR", "22"))
TIMEZONE_WIB = "Asia/Jakarta"

# Follow-up timing (hours)
FOLLOWUP_1_AFTER_HOURS = 24
FOLLOWUP_2_AFTER_HOURS = 48
MAX_FOLLOWUP_ATTEMPTS = 3

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

# Concurrency / queue tuning
MAX_AI_CONCURRENT = int(os.getenv("MAX_AI_CONCURRENT", "3"))
SEND_INTERVAL_MS = int(os.getenv("SEND_INTERVAL_MS", "3000"))

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


log = setup_logger()
