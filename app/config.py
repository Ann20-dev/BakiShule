import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    at_username: str = os.getenv("AT_USERNAME", "sandbox")
    at_api_key: str = os.getenv("AT_API_KEY", "")
    at_shortcode: str = os.getenv("AT_SHORTCODE", "")
    at_ussd_code: str = os.getenv("AT_USSD_CODE", "")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./bakishule.db")
    dry_run: bool = os.getenv("DRY_RUN", "true").lower() == "true"
    demo_mode: bool = os.getenv("DEMO_MODE", "true").lower() == "true"
    demo_teacher_phone: str = os.getenv("DEMO_TEACHER_PHONE", "+254700000001")
    demo_parent_phone: str = os.getenv("DEMO_PARENT_PHONE", "+254700000002")
    default_language: str = os.getenv("DEFAULT_LANGUAGE", "en")
    airtime_reward_kes: int = int(os.getenv("AIRTIME_REWARD_KES", "20"))


settings = Settings()


def ensure_sqlite_parent(database_url: str) -> None:
    if database_url.startswith("sqlite:///") and database_url != "sqlite:///:memory:":
        db_path = Path(database_url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)
