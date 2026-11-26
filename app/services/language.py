"""Language preferences (en | sw) for guardians and teachers, and reason translation."""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.messages import LANGUAGES, normalize_language, t, weekday_name
from app.models import GuardianAccount, Learner, Teacher


def guardian_language(db: Session, phone: str) -> str | None:
    """Saved guardian preference, or None if never chosen."""
    account = db.scalar(select(GuardianAccount).where(GuardianAccount.phone == phone))
    return account.language if account else None


def reply_language(saved: str | None) -> str:
    """Language to reply in when the input itself is language-neutral (DEFAULT_LANGUAGE, i.e. English)."""
    return saved if saved in LANGUAGES else normalize_language(settings.default_language)


def teacher_language(teacher: Teacher | None) -> str:
    return reply_language(teacher.language if teacher else None)


def set_language(db: Session, phone: str, lang: str) -> None:
    """Save the choice for every role this phone has (guardian and/or teacher)."""
    if lang not in LANGUAGES:
        raise ValueError(f"Unsupported language {lang}")
    is_guardian = db.scalar(select(Learner.id).where(Learner.guardian_phone == phone).limit(1))
    account = db.scalar(select(GuardianAccount).where(GuardianAccount.phone == phone))
    if account is None and is_guardian:
        account = GuardianAccount(phone=phone, failed_pin_attempts=0)
        db.add(account)
    if account is not None:
        account.language = lang
    for teacher in db.scalars(select(Teacher).where(Teacher.phone == phone)):
        teacher.language = lang
    db.commit()


def phone_language(db: Session, phone: str) -> str | None:
    """Preference for a phone in any role (teacher first, then guardian)."""
    teacher = db.scalar(select(Teacher).where(Teacher.phone == phone))
    if teacher and teacher.language:
        return teacher.language
    return guardian_language(db, phone)


# Risk reasons are stored in English (dashboard); translate them for USSD/SMS.
_REASON_PATTERNS = [
    (re.compile(r"(\d+) consecutive school-day absences"), "reason_streak", lambda m, lang: {"count": m[1]}),
    (re.compile(r"Attendance dropped (\d+%)"), "reason_drop", lambda m, lang: {"pct": m[1]}),
    (re.compile(r"Recurring (\w+) absence pattern"), "reason_weekday",
     lambda m, lang: {"weekday": _weekday_from_english(m[1], lang)}),
    (re.compile(r"Monthly absence clusters"), "reason_monthly", lambda m, lang: {}),
    (re.compile(r"Sibling absent on (\d+)"), "reason_sibling", lambda m, lang: {"count": m[1]}),
    (re.compile(r"Parent reported fee difficulty"), "reason_fees", lambda m, lang: {}),
    (re.compile(r"(\d+) behaviour concerns in the last (\d+) days"), "reason_behaviour",
     lambda m, lang: {"count": m[1], "days": m[2]}),
]
_ENGLISH_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _weekday_from_english(name: str, lang: str) -> str:
    return weekday_name(_ENGLISH_DAYS.index(name), lang) if name in _ENGLISH_DAYS else name


def translate_reason(reason: str, lang: str | None) -> str:
    for pattern, key, params in _REASON_PATTERNS:
        match = pattern.search(reason)
        if match:
            return t(key, lang, **params(match, lang))
    return re.sub(r"\s*\(\+\d+\)$", "", reason)
