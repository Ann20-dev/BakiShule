"""On-demand parent queries over SMS and USSD, in English and Kiswahili.

Every reply is built from system data; teachers never answer by hand.
All wording lives in app/messages.py.

Reply language rules
1. Command word clearly Kiswahili (HALI, MAHUDHURIO, TABIA, RIPOTI, MSAADA, ACHA, ANZA) -> Kiswahili
2. Command word clearly English -> English
3. Language-neutral input (1/2/3, a PIN on its own, unknown text) -> saved preference, default English
Only the explicit language commands (ENGLISH, KISWAHILI, LANG EN/SW, LUGHA EN/SW) change the
saved preference.
"""
import hashlib
import hmac
import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.messages import (
    CONCERN, DOWN, POSITIVE, PRESENT_ICON, RISK_ICONS, UP, behaviour_label, format_date, join_list, subject_label, t,
    weekday_name,
)
from app.models import AttendanceRecord, GuardianAccount, Learner, MessageLog, RiskSnapshot, utc_now_naive
from app.school_config import PIN_LOCK_MINUTES, PIN_MAX_ATTEMPTS, term_start
from app.services import at_client as at_client_module
from app.services.behaviour import behaviour_logs
from app.services.clock import demo_today
from app.services.language import guardian_language, reply_language, set_language
from app.services.sms_format import fit_sms, fit_ussd

logger = logging.getLogger(__name__)

# Command word -> (command, language). Matching is case-insensitive.
ALIASES: dict[str, tuple[str, str]] = {
    "MENU": ("menu", "en"), "HELP": ("menu", "en"), "MSAADA": ("menu", "sw"), "MENYU": ("menu", "sw"),
    "STATUS": ("status", "en"), "HALI": ("status", "sw"),
    "ATT": ("att", "en"), "ATTENDANCE": ("att", "en"), "MAHUDHURIO": ("att", "sw"),
    "BEHAVIOUR": ("behaviour", "en"), "BEHAVIOR": ("behaviour", "en"), "TABIA": ("behaviour", "sw"),
    "REPORT": ("report", "en"), "RIPOTI": ("report", "sw"),
}
# Opt-out / opt-in words are handled by the check-in flow (app/routes/sms.py).
STOP_WORDS = {"STOP": "en", "ACHA": "sw"}
START_WORDS = {"START": "en", "ANZA": "sw"}
LANGUAGE_WORDS = {"ENGLISH": "en", "KIINGEREZA": "en", "KISWAHILI": "sw", "SWAHILI": "sw"}
LANGUAGE_PREFIXES = {"LANG", "LUGHA", "LANGUAGE"}
LANGUAGE_CODES = {"EN": "en", "ENG": "en", "ENGLISH": "en", "SW": "sw", "KISWAHILI": "sw", "SWAHILI": "sw"}

PIN_COMMANDS = {"behaviour", "report"}
COMBINABLE = {"status", "att"}  # multi-child: these return a combined summary
SPACE, NEWLINE = " ", "\n"  # SMS part separators: sentences vs lists


@dataclass
class ParsedCommand:
    command: str
    lang: str | None  # language of the command word; None = not stated
    word: str
    child: int | None = None
    pin: str | None = None


def _tokens(text: str) -> list[str]:
    return [token for token in re.split(r"[\s,.*#:;-]+", (text or "").strip()) if token]


def parse_command(text: str) -> ParsedCommand | None:
    """'report 2 4821' -> ParsedCommand('report', 'en', 'REPORT', child=2, pin='4821').
    'LUGHA SW' / 'KISWAHILI' -> ParsedCommand('lang', 'sw', ...)."""
    tokens = _tokens(text)
    if not tokens:
        return None
    word = tokens[0].upper()
    if word in LANGUAGE_WORDS:
        return ParsedCommand(command="lang", lang=LANGUAGE_WORDS[word], word=word)
    if word in LANGUAGE_PREFIXES:
        chosen = LANGUAGE_CODES.get(tokens[1].upper()) if len(tokens) > 1 else None
        return ParsedCommand(command="lang", lang=chosen, word=word)
    if word not in ALIASES:
        return None
    command, lang = ALIASES[word]
    parsed = ParsedCommand(command=command, lang=lang, word=word)
    for token in tokens[1:]:
        if token.isdigit() and len(token) == 4 and parsed.pin is None:
            parsed.pin = token
        elif token.isdigit() and len(token) <= 2 and parsed.child is None:
            parsed.child = int(token)
    return parsed


def mask_pins(text: str | None) -> str | None:
    return re.sub(r"\b\d{4}\b", "****", text) if text else text


# ---------- guardian accounts & PINs ----------

def hash_pin(pin: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 100_000).hex()
    return digest, salt


def set_pin(db: Session, phone: str, pin: str) -> GuardianAccount:
    if not (pin.isdigit() and len(pin) == 4):
        raise ValueError("PIN must be 4 digits")
    account = get_account(db, phone, create=True)
    account.pin_hash, account.pin_salt = hash_pin(pin)
    account.failed_pin_attempts = 0
    account.locked_until = None
    db.flush()
    return account


def get_account(db: Session, phone: str, create: bool = False) -> GuardianAccount | None:
    account = db.scalar(select(GuardianAccount).where(GuardianAccount.phone == phone))
    if not account and create:
        account = GuardianAccount(phone=phone, failed_pin_attempts=0)  # language stays null until chosen
        db.add(account)
        db.flush()
    return account


def guardian_learners(db: Session, phone: str) -> list[Learner]:
    return list(db.scalars(select(Learner).where(Learner.guardian_phone == phone).order_by(Learner.id)))


def _local_time(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone)).strftime("%H:%M")


def check_pin(account: GuardianAccount | None, pin: str | None, lang: str, example: str) -> tuple[bool, str, str]:
    """Returns (ok, reply_text_if_not_ok, status)."""
    now = utc_now_naive()
    if account is None or not account.pin_hash:
        return False, t("no_pin", lang), "no_pin"
    if account.locked_until and account.locked_until > now:
        return False, t("pin_locked", lang, time=_local_time(account.locked_until)), "pin_locked"
    if not pin:
        return False, t("pin_required", lang, example=example), "pin_required"
    digest, _ = hash_pin(pin, account.pin_salt)
    if hmac.compare_digest(digest, account.pin_hash):
        account.failed_pin_attempts = 0
        account.locked_until = None
        return True, "", "ok"
    account.failed_pin_attempts = (account.failed_pin_attempts or 0) + 1
    if account.failed_pin_attempts >= PIN_MAX_ATTEMPTS:
        account.failed_pin_attempts = 0
        account.locked_until = now + timedelta(minutes=PIN_LOCK_MINUTES)
        return False, t("pin_locked", lang, time=_local_time(account.locked_until)), "pin_locked"
    return False, t("pin_wrong", lang, left=PIN_MAX_ATTEMPTS - account.failed_pin_attempts), "pin_wrong"


# ---------- rate limiting ----------

def local_day_start_utc() -> datetime:
    zone = ZoneInfo(settings.timezone)
    local_midnight = datetime.now(zone).replace(hour=0, minute=0, second=0, microsecond=0)
    return local_midnight.astimezone(timezone.utc).replace(tzinfo=None)


def rate_limit_state(db: Session, phone: str) -> str:
    """'ok' if under the daily limit; 'notify' the first time it is hit today; then 'silent'."""
    today_logs = list(
        db.scalars(
            select(MessageLog).where(MessageLog.phone == phone, MessageLog.created_at >= local_day_start_utc())
        )
    )
    if sum(log.counted for log in today_logs) < settings.parent_daily_query_limit:
        return "ok"
    return "silent" if any(log.status == "rate_limited" for log in today_logs) else "notify"


# ---------- data helpers ----------

def _dm(day: date) -> str:
    return day.strftime("%d/%m")


def _pct(present: int, total: int) -> str:
    return f"{round(present / total * 100)}%" if total else "n/a"


def _records(db: Session, learner_ids: list[int], start: date, end: date) -> list[AttendanceRecord]:
    if not learner_ids:
        return []
    return list(
        db.scalars(
            select(AttendanceRecord)
            .where(
                AttendanceRecord.learner_id.in_(learner_ids),
                AttendanceRecord.date >= start,
                AttendanceRecord.date <= end,
            )
            .order_by(AttendanceRecord.date)
        )
    )


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _latest_risk(db: Session, learner_id: int) -> RiskSnapshot | None:
    return db.scalar(
        select(RiskSnapshot)
        .where(RiskSnapshot.learner_id == learner_id)
        .order_by(RiskSnapshot.date.desc(), RiskSnapshot.id.desc())
        .limit(1)
    )


def first_name(learner: Learner) -> str:
    parts = learner.name.split()
    return learner.name if len(parts) > 1 and parts[1].isdigit() else parts[0]  # "Learner 01" stays whole


def teacher_title(teacher, lang: str) -> str:
    return t("teacher_title", lang, surname=teacher.name.split()[-1]) if teacher else ""


def _today_record(db: Session, learner: Learner, today: date) -> AttendanceRecord | None:
    return next(iter(_records(db, [learner.id], today, today)), None)


def _today_text(db: Session, learner: Learner, today: date, lang: str, short: bool) -> str:
    record = _today_record(db, learner, today)
    if record is None:
        return t("short_unmarked" if short else "today_unmarked", lang)
    if record.present:
        return t("short_present", lang) if short else t("today_present", lang, icon=PRESENT_ICON)
    return t("short_absent", lang) if short else t("today_absent", lang, icon=CONCERN)


# ---------- reply builders: (parts, separator), most important part first ----------

def build_menu(lang: str) -> tuple[list[str], str]:
    return [t("menu", lang)], NEWLINE


def build_status(db: Session, learner: Learner, today: date, lang: str) -> tuple[list[str], str]:
    parts = [
        t("status_line", lang, name=learner.name, cls=learner.classroom.name,
          date=format_date(today, lang), today=_today_text(db, learner, today, lang, short=False))
    ]
    latest = behaviour_logs(db, learner.id, end=today, limit=1)
    if latest:
        log = latest[0]
        subject = subject_label(log.subject, lang)
        parts.append(t(
            "last_note", lang,
            icon=POSITIVE if log.sentiment == "positive" else CONCERN,
            label=behaviour_label(log.code, lang),
            subject=f", {subject}" if subject else "",
            teacher=teacher_title(log.teacher or learner.classroom.teacher, lang),
        ))
    else:
        parts.append(t("no_notes", lang))
    parts.append(t("status_more", lang))
    return parts, SPACE


def _attendance_numbers(db: Session, learner: Learner, today: date) -> dict:
    week = _records(db, [learner.id], _week_start(today), today)
    start = term_start(today)
    term = _records(db, [learner.id], start, today)
    class_term = _records(db, [item.id for item in learner.classroom.learners], start, today)
    return {
        "attended": sum(record.present for record in week),
        "total": len(week),
        "missed": [record.date for record in week if not record.present],
        "term": _pct(sum(r.present for r in term), len(term)),
        "avg": _pct(sum(r.present for r in class_term), len(class_term)),
    }


def build_attendance(db: Session, learner: Learner, today: date, lang: str) -> tuple[list[str], str]:
    numbers = _attendance_numbers(db, learner, today)
    days = join_list([weekday_name(day.weekday(), lang) for day in numbers["missed"]], lang)
    missed = t("att_missed_days", lang, days=days) if days else t("att_no_missed", lang)
    return [
        t("att_week_line", lang, name=learner.name, attended=numbers["attended"], total=numbers["total"],
          missed=missed),
        t("att_term_line", lang, pct=numbers["term"]),
        t("att_class_avg", lang, pct=numbers["avg"]),
    ], SPACE


def build_behaviour(db: Session, learner: Learner, today: date, lang: str) -> tuple[list[str], str]:
    logs = behaviour_logs(db, learner.id, term_start(today), today)
    if not logs:
        return [t("beh_none", lang)], NEWLINE
    positive = sum(log.sentiment == "positive" for log in logs)
    parts = [t("beh_header", lang, name=learner.name, positive=positive, pos=POSITIVE,
               concern=len(logs) - positive, con=CONCERN)]
    for log in logs[:5]:
        icon = POSITIVE if log.sentiment == "positive" else CONCERN
        parts.append(f"{icon} {_dm(log.date)} {behaviour_label(log.code, lang, short=True)}")
    return parts, NEWLINE


def build_report(db: Session, learner: Learner, today: date, lang: str) -> tuple[list[str], str]:
    week_start = _week_start(today)
    this_week = _records(db, [learner.id], week_start, today)
    last_week = _records(db, [learner.id], week_start - timedelta(days=7), week_start - timedelta(days=1))
    now = round(sum(r.present for r in this_week) / len(this_week) * 100) if this_week else None
    before = round(sum(r.present for r in last_week) / len(last_week) * 100) if last_week else None
    if now is None:
        attendance = t("report_attendance_only", lang, pct="n/a")
    elif before is None:
        attendance = t("report_attendance_only", lang, pct=f"{now}%")
    elif now == before:
        attendance = t("report_attendance_same", lang, pct=f"{now}%")
    else:
        attendance = t("report_attendance", lang, pct=f"{now}%", arrow=f" {DOWN if now < before else UP}",
                       previous=f"{before}%")
    week_logs = behaviour_logs(db, learner.id, week_start, today)
    positive = sum(log.sentiment == "positive" for log in week_logs)
    concern = len(week_logs) - positive
    snapshot = _latest_risk(db, learner.id)
    level = snapshot.level if snapshot else None
    absences = [r.date for r in this_week if not r.present]
    name = first_name(learner)
    if absences:
        tip = t("tip_attendance", lang, first=name, day=weekday_name(absences[-1].weekday(), lang))
    elif concern:
        tip = t("tip_behaviour", lang, first=name)
    elif level in {"watch", "at_risk", "critical"}:
        tip = t("tip_checkin", lang, first=name)
    else:
        tip = t("tip_praise", lang, first=name)
    return [
        t("report_title", lang, name=learner.name, cls=learner.classroom.name),
        attendance,
        t("report_behaviour", lang, positive=positive, pos=POSITIVE, concern=concern, con=CONCERN),
        t("report_status", lang, icon=f"{RISK_ICONS[level]} " if level else "",
          risk=t(f"risk_{level}" if level else "risk_none", lang)),
        tip,
    ], SPACE


def build_combined(
    db: Session, learners: list[Learner], today: date, lang: str, command: str, word: str
) -> tuple[list[str], str]:
    parts = []
    for learner in learners:
        if command == "status":
            parts.append(t("status_short", lang, name=learner.name,
                           today=_today_text(db, learner, today, lang, short=True)))
        else:
            numbers = _attendance_numbers(db, learner, today)
            parts.append(t("att_short", lang, name=learner.name, attended=numbers["attended"],
                           total=numbers["total"], pct=numbers["term"]))
    parts.append(t("combined_hint", lang, command=word))
    return parts, NEWLINE


BUILDERS = {
    "status": build_status,
    "att": build_attendance,
    "behaviour": build_behaviour,
    "report": build_report,
}


def render_sms(built: tuple[list[str], str], lang: str) -> str:
    parts, sep = built
    return fit_sms(parts, lang, sep=sep)


def render_ussd(built: tuple[list[str], str]) -> str:
    parts, _ = built
    return fit_ussd(parts)  # USSD: one part per line


def _choose_child(learners: list[Learner], lang: str, word: str, needs_pin: bool) -> str:
    children = ", ".join(f"{index} {learner.name}" for index, learner in enumerate(learners, start=1))
    example = f"{word} 1" + (" <PIN>" if needs_pin else "")
    return t("choose_child_sms", lang, count=len(learners), children=children, example=example)


# ---------- main entry points ----------

def run_query(
    db: Session,
    phone: str,
    command: str | None,
    lang: str | None,
    *,
    child: int | None = None,
    pin: str | None = None,
    channel: str = "sms",
    word: str | None = None,
    inbound_text: str | None = None,
) -> MessageLog:
    """Answer one parent query and log it. The reply is in log.reply_text (None = send nothing).

    `lang` is the language of the command word (None if the input was language-neutral).
    """
    learners = guardian_learners(db, phone)
    reply_lang = lang or reply_language(guardian_language(db, phone))
    word = word or (command or "").upper()
    built: tuple[list[str], str] | None = None
    learner_id = None
    counted = True
    log_lang: str | None = reply_lang

    state = rate_limit_state(db, phone)
    if state != "ok":
        status, counted = "rate_limited", False
        if state == "notify" or channel == "ussd":
            built = ([t("rate_limited", reply_lang, limit=settings.parent_daily_query_limit)], SPACE)
        else:
            status = "rate_limited_silent"
    elif not learners:
        status, log_lang = "unknown_number", None
        built = ([t("not_registered")], SPACE)  # bilingual: we don't know their language
    elif command == "lang":
        if lang is None:
            status, log_lang = "language_prompt", None
            built = ([t("lang_prompt")], SPACE)
        else:
            set_language(db, phone, lang)
            status = "language_set"
            built = build_menu(lang)
    elif command == "pin_only":
        status = "pin_only"
        built = ([t("pin_only", reply_lang, example="1234")], SPACE)
    elif command == "menu":
        status = "ok"
        built = build_menu(reply_lang)
    else:
        account = get_account(db, phone, create=True)
        status = "ok"
        ok = True
        if command in PIN_COMMANDS:
            example = f"{word}{' 1' if len(learners) > 1 and child is None else ''} 1234"
            ok, message, status = check_pin(account, pin, reply_lang, example)
            if not ok:
                built = ([message], SPACE)
        if ok:
            today = demo_today(db)
            if child is None and len(learners) > 1:
                if command in COMBINABLE:
                    built, status = build_combined(db, learners, today, reply_lang, command, word), "ok_combined"
                else:
                    built = ([_choose_child(learners, reply_lang, word, command in PIN_COMMANDS)], SPACE)
                    status = "choose_child"
            elif child is not None and not 1 <= child <= len(learners):
                built = ([_choose_child(learners, reply_lang, word, command in PIN_COMMANDS)], SPACE)
                status = "choose_child"
            else:
                learner = learners[(child or 1) - 1]
                learner_id = learner.id
                built = BUILDERS[command](db, learner, today, reply_lang)

    reply = None
    if built:
        reply = render_ussd(built) if channel == "ussd" else render_sms(built, reply_lang)
    log = MessageLog(
        phone=phone,
        channel=channel,
        command=command,
        language=log_lang,
        inbound_text=mask_pins(inbound_text),
        reply_text=reply,
        status=status,
        counted=counted,
        learner_id=learner_id or (learners[0].id if learners else None),
        delivery_status="pending" if reply and channel == "sms" else None,
    )
    db.add(log)
    db.commit()
    return log


def handle_sms_query(db: Session, phone: str, text: str) -> MessageLog | None:
    """Handle commands, language commands, a bare PIN, and unknown numbers.

    Returns None for registered guardians sending check-in replies (1/2/3, STOP/ACHA, START/ANZA,
    free text), which app/routes/sms.py handles."""
    parsed = parse_command(text)
    if parsed:
        return run_query(
            db, phone, parsed.command, parsed.lang, child=parsed.child, pin=parsed.pin,
            word=parsed.word, inbound_text=text,
        )
    stripped = (text or "").strip()
    if guardian_learners(db, phone):
        if stripped.isdigit() and len(stripped) == 4:  # a PIN on its own: never forward it to a teacher
            return run_query(db, phone, "pin_only", None, inbound_text=text)
        return None
    if stripped.upper() in STOP_WORDS:  # never text back a STOP
        log = MessageLog(phone=phone, channel="sms", inbound_text=text, status="unknown_stop", language=None)
        db.add(log)
        db.commit()
        return log
    return run_query(db, phone, None, None, inbound_text=text)


def language_prompt_if_needed(db: Session, phone: str, text: str) -> MessageLog | None:
    """First contact from a guardian with no language: send the bilingual welcome once."""
    parsed = parse_command(text)
    if parsed and parsed.command == "lang":
        return None
    if not guardian_learners(db, phone) or guardian_language(db, phone):
        return None
    already = db.scalar(
        select(MessageLog.id).where(MessageLog.phone == phone, MessageLog.status == "language_welcome").limit(1)
    )
    if already:
        return None
    log = MessageLog(
        phone=phone, channel="sms", command="lang", language=None, inbound_text=None,
        reply_text=t("sms_welcome"), status="language_welcome", counted=False, delivery_status="pending",
    )
    db.add(log)
    db.commit()
    return log


def reset_language(db: Session, phone: str) -> None:
    """Demo helper: forget the language for this phone (guardian and teacher) so the welcome shows again."""
    from app.models import Teacher

    account = get_account(db, phone)
    if account:
        account.language = None
    for teacher in db.scalars(select(Teacher).where(Teacher.phone == phone)):
        teacher.language = None
    db.execute(delete(MessageLog).where(MessageLog.phone == phone, MessageLog.status == "language_welcome"))
    db.commit()


def deliver_message_log(log_id: int, db: Session | None = None) -> None:
    """Send a logged reply by SMS (respects DRY_RUN) and record the result."""
    from app.db import SessionLocal

    own_session = db is None
    db = db or SessionLocal()
    try:
        log = db.get(MessageLog, log_id)
        if not log or not log.reply_text:
            return
        try:
            result = at_client_module.at_client.send_sms(log.phone, log.reply_text)
        except Exception as error:  # keep the log even if sending blows up
            logger.exception("Reply SMS failed")
            result = {"status": "failed", "error": str(error)}
        log.delivery_status = result.get("status", "submitted")
        log.at_response = {key: value for key, value in result.items() if key != "raw"}
        db.commit()
    finally:
        if own_session:
            db.close()
