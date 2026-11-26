import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    at_username: str = os.getenv("AT_USERNAME", "sandbox")
    at_api_key: str = os.getenv("AT_API_KEY", "")
    # Sender ID for outbound SMS (sandbox default: AFTKNG). AT_SHORTCODE kept as a fallback.
    at_sender_id: str = os.getenv("AT_SENDER_ID") or os.getenv("AT_SHORTCODE", "")
    at_ussd_code: str = os.getenv("AT_USSD_CODE", "")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./bakishule.db")
    dry_run: bool = os.getenv("DRY_RUN", "true").lower() == "true"
    demo_mode: bool = os.getenv("DEMO_MODE", "true").lower() == "true"
    demo_teacher_phone: str = os.getenv("DEMO_TEACHER_PHONE", "+254700000001")
    demo_parent_phone: str = os.getenv("DEMO_PARENT_PHONE", "+254700000002")
    default_language: str = os.getenv("DEFAULT_LANGUAGE", "en")
    airtime_reward_kes: int = int(os.getenv("AIRTIME_REWARD_KES", "20"))
    # Parent SMS/USSD queries
    demo_guardian_pin: str = os.getenv("DEMO_GUARDIAN_PIN", "1234")
    parent_daily_query_limit: int = int(os.getenv("PARENT_DAILY_QUERY_LIMIT", "10"))
    timezone: str = os.getenv("TIMEZONE", "Africa/Nairobi")
    # Emojis (⭐ ⚠️ ✅ ...) in SMS replies; replaced by plain text if a reply would exceed 2 segments
    sms_use_emoji: bool = os.getenv("SMS_USE_EMOJI", "true").lower() == "true"
    # AI chat: free-text parent SMS ("How is my child doing?") answered by Claude
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    ai_chat_enabled: bool = os.getenv("AI_CHAT_ENABLED", "true").lower() == "true"
    ai_model: str = os.getenv("AI_MODEL", "claude-opus-5-5")
    # Background weekly-report job (Fridays 16:00 local time)
    enable_scheduler: bool = os.getenv("ENABLE_SCHEDULER", "true").lower() == "true"


settings = Settings()


def ensure_sqlite_parent(database_url: str) -> None:
    if database_url.startswith("sqlite:///") and database_url != "sqlite:///:memory:":
        db_path = Path(database_url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)
