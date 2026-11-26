"""USSD for teachers and parents, in English and Kiswahili. All text comes from app/messages.py.

AT sends the whole input chain on every request (text="1*2*07"), so each screen is derived from it.
First-time users (no language saved) answer a language screen first; because that answer stays at
the front of the chain for the rest of the session, sessions that started with it are remembered.
"""
import re
import time
from collections.abc import Callable
from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.messages import CONCERN, POSITIVE, behaviour_label, format_date, normalize_language, subject_label, t
from app.models import AttendanceRecord, ClassRoom, Learner, MessageLog, ParentReply, RiskSnapshot, Teacher
from app.school_config import BEHAVIOUR_CODES, SUBJECTS
from app.services.attendance import run_escalations, save_class_attendance
from app.services.behaviour import log_behaviour
from app.services.clock import demo_today
from app.services.escalation import maybe_escalate
from app.services.language import phone_language, set_language, teacher_language, translate_reason
from app.services.parent_queries import PIN_COMMANDS, guardian_learners, run_query
from app.services.phone import normalize_number
from app.services.risk import recompute_learner

router = APIRouter()

MAX_SCREEN = 180  # USSD screens are cut off around 182 characters
HOME = "00"
BACK = "0"
LANGUAGE_CHOICES = {"1": "en", "2": "sw"}
FLAGGED = {"watch", "at_risk", "critical"}
TEACHER_ACTIONS = {"1": "attendance", "2": "summary", "3": "at_risk", "4": "behaviour", "5": "lookup"}
PARENT_ACTIONS = {"1": "status", "2": "att", "3": "behaviour", "4": "report", "5": "contact"}

# session_id -> time the session answered the first-time language screen
_LANGUAGE_SESSIONS: dict[str, float] = {}
_SESSION_TTL = 600


def _remember_language_session(session_id: str | None) -> None:
    if not session_id:
        return
    now = time.monotonic()
    for key in [key for key, started in _LANGUAGE_SESSIONS.items() if now - started > _SESSION_TTL]:
        _LANGUAGE_SESSIONS.pop(key, None)
    _LANGUAGE_SESSIONS[session_id] = now


# ---------- formatting helpers ----------

def _screen(kind: str, lines: list[str]) -> str:
    """Join lines into a CON/END screen, dropping trailing lines that don't fit."""
    lines = [line for line in lines if line]
    text = f"{kind} " + "\n".join(lines)
    while len(text) > MAX_SCREEN and len(lines) > 1:
        lines = lines[:-1]
        text = f"{kind} " + "\n".join(lines)
    return text[:MAX_SCREEN]


def _con(*lines: str) -> str:
    return _screen("CON", list(lines))


def _end(*lines: str) -> str:
    return _screen("END", list(lines))


def _bilingual(key: str) -> str:
    sw, en = t(key, "sw"), t(key, "en")
    return sw if sw == en else f"{sw} / {en}"


def _pct(present: int, total: int) -> str:
    return f"{round(present / total * 100)}%" if total else "n/a"


# ---------- data helpers ----------

def _records(db: Session, learner_ids: list[int], start: date, end: date) -> list[AttendanceRecord]:
    if not learner_ids:
        return []
    return list(
        db.scalars(
            select(AttendanceRecord).where(
                AttendanceRecord.learner_id.in_(learner_ids),
                AttendanceRecord.date >= start,
                AttendanceRecord.date <= end,
            )
        )
    )


def _latest_risk(db: Session, learner_ids: list[int]) -> dict[int, RiskSnapshot]:
    if not learner_ids:
        return {}
    latest: dict[int, RiskSnapshot] = {}
    for snapshot in db.scalars(
        select(RiskSnapshot)
        .where(RiskSnapshot.learner_id.in_(learner_ids))
        .order_by(RiskSnapshot.date.desc(), RiskSnapshot.id.desc())
    ):
        latest.setdefault(snapshot.learner_id, snapshot)
    return latest


def _flagged(db: Session, classroom: ClassRoom) -> list[RiskSnapshot]:
    latest = _latest_risk(db, [learner.id for learner in classroom.learners])
    flagged = [snap for snap in latest.values() if snap.level in FLAGGED]
    return sorted(flagged, key=lambda snap: snap.score, reverse=True)


def _marked_today(db: Session, classroom: ClassRoom, today: date) -> bool:
    return bool(_records(db, [learner.id for learner in classroom.learners], today, today))


def _parse_rolls(raw: str) -> set[str]:
    raw = raw.strip()
    if raw == "0":
        return set()
    return {token for token in re.split(r"[\s,.#]+", raw) if token}


def _find_learner(classroom: ClassRoom, roll: str) -> Learner | None:
    roll = roll.strip()
    learner = next((item for item in classroom.learners if item.roll_number == roll), None)
    if not learner and roll.isdigit():
        learner = next((item for item in classroom.learners if item.roll_number.lstrip("0") == roll.lstrip("0")), None)
    return learner


def _level(level: str, lang: str) -> str:
    return t(f"level_{level}", lang)


# ---------- language screens ----------

def _language_screen() -> str:
    return f"CON {t('language_screen')}"


def _change_language(db: Session, phone: str, steps: list[str], menu: Callable[[str], list[str]]):
    """Handles '<change-language option>*<1|2>*...'. Returns a screen, or (lang, remaining steps)."""
    if not steps:
        return _language_screen()
    lang = LANGUAGE_CHOICES.get(steps[0])
    if not lang:
        return f"END {_bilingual('invalid_choice')}"
    set_language(db, phone, lang)
    if len(steps) == 1:
        return _con(t("language_changed", lang), *menu(lang)[1:])  # confirmation replaces the title line
    return lang, steps[1:]


# ---------- teacher screens ----------

def _teacher_menu_lines(lang: str, is_parent: bool) -> list[str]:
    lines = [t("teacher_menu_title", lang)]
    lines += [f"{key}. {t(f'teacher_menu_{key}', lang)}" for key in TEACHER_ACTIONS]
    number = len(TEACHER_ACTIONS) + 1
    if is_parent:
        lines.append(f"{number}. {t('teacher_menu_parent', lang)}")
        number += 1
    lines.append(f"{number}. {t('menu_change_language', lang)}")
    return lines


def _teacher_option_numbers(is_parent: bool) -> tuple[str | None, str]:
    """(parent-menu option, change-language option)."""
    number = len(TEACHER_ACTIONS) + 1
    if is_parent:
        return str(number), str(number + 1)
    return None, str(number)


def _class_selection(db: Session, classes: list[ClassRoom], action: str, today: date, lang: str) -> str:
    lines = [t("select_class", lang)]
    for index, room in enumerate(classes, start=1):
        label = f"{index}. {room.name} ({len(room.learners)})"
        if action == "attendance" and _marked_today(db, room, today):
            label += f" - {t('done_today', lang)}"
        lines.append(label)
    lines.append(t("nav_back", lang))
    return _con(*lines)


def _learner_detail(db: Session, learner: Learner, today: date, lang: str) -> str:
    month = _records(db, [learner.id], today - timedelta(days=30), today)
    present = sum(record.present for record in month)
    absences = sorted(record.date for record in month if not record.present)
    snapshot = _latest_risk(db, [learner.id]).get(learner.id)
    reply = db.scalar(
        select(ParentReply).where(ParentReply.learner_id == learner.id).order_by(ParentReply.received_at.desc())
    )
    lines = [f"{learner.roll_number} {learner.name[:22]} ({learner.classroom.name})"]
    if snapshot:
        lines.append(t("det_risk", lang, level=_level(snapshot.level, lang), score=snapshot.score))
    lines.append(t("det_30_days", lang, pct=_pct(present, len(month)), absent=len(absences)))
    if absences:
        lines.append(t("det_last_absent", lang, date=format_date(absences[-1], lang, short=True)))
    if reply:
        lines.append(t("det_parent_said", lang, text=reply.raw_text[:20]))
    lines.append(t("det_guardian", lang, name=learner.guardian_name[:14], phone=learner.guardian_phone))
    if snapshot:
        lines.extend(f"- {translate_reason(reason, lang)[:48]}" for reason in snapshot.reasons[:3])
    return _end(*lines)


def _attendance_flow(
    db: Session, classroom: ClassRoom, steps: list[str], today: date, lang: str, defer: Callable | None
) -> str:
    learners = sorted(classroom.learners, key=lambda learner: learner.roll_number)
    by_roll = {learner.roll_number: learner for learner in learners}
    total = len(learners)

    if not steps:
        lines = [t("att_screen_header", lang, cls=classroom.name, date=format_date(today, lang, short=True),
                   total=total)]
        if _marked_today(db, classroom, today):
            lines.append(t("att_already_marked", lang))
        lines += [t("att_enter", lang), t("att_all_present", lang), t("nav_home", lang)]
        return _con(*lines)

    # After an "Unknown roll" prompt the next entry is appended to the chain; skip the bad one.
    while len(steps) > 1 and (not steps[0].strip() or _parse_rolls(steps[0]) - by_roll.keys()):
        steps = steps[1:]
    absent_input = steps[0].strip()
    if not absent_input:
        return _con(t("att_enter_blank", lang))
    rolls = _parse_rolls(absent_input)
    invalid = sorted(rolls - by_roll.keys())
    if invalid:
        return _con(
            t("att_unknown_roll", lang, rolls=", ".join(invalid)[:40]),
            t("att_roll_range", lang, cls=classroom.name, first=learners[0].roll_number,
              last=learners[-1].roll_number) if learners else "",
            t("att_enter_again", lang),
        )

    if len(steps) == 1:
        absent = [by_roll[roll] for roll in sorted(rolls)]
        lines = [
            t("att_confirm", lang, cls=classroom.name, date=format_date(today, lang, short=True)),
            t("att_counts", lang, present=total - len(absent), total=total, absent=len(absent)),
        ]
        if absent:
            names = ", ".join(f"{learner.roll_number} {learner.name[:14]}" for learner in absent[:3])
            if len(absent) > 3:
                names += " " + t("more", lang, count=len(absent) - 3)
            lines.append(t("att_absent_list", lang, names=names))
        lines += [t("option_save", lang), t("option_cancel", lang)]
        return _con(*lines)

    if len(steps) == 2 and steps[1] in {"0", "1"}:
        if steps[1] == "0":
            return _end(t("att_cancelled", lang))
        try:
            count = save_class_attendance(db, classroom, rolls, defer=defer)
        except ValueError:
            return _end(t("att_invalid_roll", lang))
        flagged = _flagged(db, classroom)
        absent_flagged = [snap for snap in flagged if snap.learner.roll_number in rolls]
        lines = [
            t("att_saved", lang, count=count, cls=classroom.name),
            t("att_saved_counts", lang, present=count - len(rolls), absent=len(rolls)),
            t("att_flagged", lang, count=len(flagged)),
        ]
        if absent_flagged:
            lines.append(t("att_parents_notified", lang, count=len(absent_flagged)))
        return _end(*lines)

    return _end(t("att_invalid_entry", lang))


def _summary(db: Session, classroom: ClassRoom, today: date, lang: str) -> str:
    ids = [learner.id for learner in classroom.learners]
    week_start = today - timedelta(days=today.weekday())
    month = _records(db, ids, today - timedelta(days=30), today)
    week = [record for record in month if record.date >= week_start]
    todays = [record for record in month if record.date == today]
    flagged = _flagged(db, classroom)
    critical = sum(snap.level == "critical" for snap in flagged)

    lines = [t("sum_header", lang, cls=classroom.name, date=format_date(today, lang, short=True))]
    if todays:
        present = sum(record.present for record in todays)
        lines.append(t("sum_today", lang, present=present, absent=len(todays) - present,
                       pct=_pct(present, len(todays))))
    else:
        lines.append(t("sum_unmarked", lang))
    lines.append(t("sum_week", lang, pct=_pct(sum(r.present for r in week), len(week))))
    lines.append(t("sum_month", lang, pct=_pct(sum(r.present for r in month), len(month))))
    lines.append(t("sum_flagged", lang, count=len(flagged), critical=critical))
    absent_rolls = sorted(r.learner.roll_number for r in todays if not r.present)
    if absent_rolls:
        lines.append(t("sum_absent", lang, rolls=" ".join(absent_rolls)[:60]))
    return _end(*lines)


def _at_risk_flow(db: Session, classroom: ClassRoom, steps: list[str], today: date, lang: str) -> str:
    flagged = _flagged(db, classroom)[:6]
    if not flagged:
        return _end(t("ar_none", lang, cls=classroom.name))
    if not steps:
        lines = [t("ar_header", lang, cls=classroom.name, count=len(flagged))]
        lines += [
            f"{i}. {snap.learner.roll_number} {snap.learner.name[:12]} {_level(snap.level, lang)} {snap.score}"
            for i, snap in enumerate(flagged, start=1)
        ]
        lines.append(t("ar_reply_for_details", lang))
        return _con(*lines)
    choice = steps[0]
    if choice.isdigit() and 1 <= int(choice) <= len(flagged):
        return _learner_detail(db, flagged[int(choice) - 1].learner, today, lang)
    return _end(t("invalid_choice", lang))


def _lookup_flow(db: Session, classroom: ClassRoom, steps: list[str], today: date, lang: str) -> str:
    if not steps:
        return _con(t("lookup_enter_roll", lang, cls=classroom.name), t("nav_home", lang))
    roll = steps[0].strip()
    learner = _find_learner(classroom, roll)
    if not learner:
        return _end(t("lookup_not_found", lang, roll=roll[:6], cls=classroom.name))
    return _learner_detail(db, learner, today, lang)


def _behaviour_flow(
    db: Session, teacher: Teacher, classroom: ClassRoom, steps: list[str], today: date, lang: str,
    defer: Callable | None,
) -> str:
    """4 > class > roll > behaviour code > subject (optional) > saved."""
    if not steps:
        return _con(t("lookup_enter_roll", lang, cls=classroom.name), t("nav_home", lang))
    while len(steps) > 1 and not _find_learner(classroom, steps[0]):  # skip earlier invalid rolls
        steps = steps[1:]
    learner = _find_learner(classroom, steps[0])
    if not learner:
        return _con(t("beh_no_roll", lang, roll=steps[0][:6], cls=classroom.name), t("beh_enter_again", lang))
    if len(steps) == 1:
        # Short header so all six codes fit on one USSD screen in both languages.
        lines = [t("beh_choose", lang, roll=learner.roll_number, name=learner.name.split()[0][:10])]
        for code, entry in BEHAVIOUR_CODES.items():
            icon = POSITIVE if entry["sentiment"] == "positive" else CONCERN
            lines.append(f"{code}. {behaviour_label(code, lang)} {icon}")
        return _con(*lines)
    code = steps[1]
    if not (code.isdigit() and int(code) in BEHAVIOUR_CODES):
        return _end(t("beh_invalid_code", lang))
    code_num = int(code)
    if len(steps) == 2:
        lines = [t("beh_subject_title", lang)]
        lines += [f"{key}. {t(f'subject_{key}', lang)}" for key in SUBJECTS]
        lines.append(t("option_skip", lang))
        return _con(*lines)
    choice = steps[2]
    if choice != "0" and not (choice.isdigit() and int(choice) in SUBJECTS):
        return _end(t("beh_invalid_subject", lang))
    subject = None if choice == "0" else SUBJECTS[int(choice)]
    log_behaviour(db, learner, teacher, code_num, today, subject)
    snapshot, previous_level = recompute_learner(db, learner, today)
    db.commit()
    if defer is not None:
        defer(run_escalations, [(learner.id, snapshot.id, previous_level)])
    else:
        maybe_escalate(db, learner, snapshot, previous_level)
        db.commit()
    icon = POSITIVE if BEHAVIOUR_CODES[code_num]["sentiment"] == "positive" else CONCERN
    shown_subject = subject_label(subject, lang)
    return _end(
        t("beh_saved", lang, roll=learner.roll_number, name=learner.name[:20]),
        f"{icon} {behaviour_label(code_num, lang)}" + (f" ({shown_subject})" if shown_subject else ""),
        t("beh_parent_can_view", lang),
    )


# ---------- parent screens ----------

def _parent_menu_lines(learners: list[Learner], lang: str) -> list[str]:
    lines = [t("parent_menu_title", lang, name=learners[0].guardian_name[:24])]
    lines += [f"{key}. {t(f'parent_menu_{key}', lang)}" for key in PARENT_ACTIONS]
    lines.append(f"{len(PARENT_ACTIONS) + 1}. {t('menu_change_language', lang)}")
    return lines


def send_contact_message(learner_id: int, phone: str, text: str, db: Session | None = None) -> None:
    """Forward a parent's 'Contact school' message to the class teacher, in the teacher's language."""
    from app.db import SessionLocal
    from app.services.escalation import _log_send

    own = db is None
    db = db or SessionLocal()
    try:
        learner = db.get(Learner, learner_id)
        if not learner:
            return
        teacher = learner.classroom.teacher
        message = t("teacher_parent_message", teacher_language(teacher), name=learner.name, text=text[:100])
        _log_send(db, learner, "staff_alert", teacher.phone, message[:160], {"category": "parent_contact"})
    finally:
        if own:
            db.close()


def _parent_flow(
    db: Session, phone: str, learners: list[Learner], parts: list[str], lang: str, defer: Callable | None
) -> str:
    """Guardian USSD menu, reusing the SMS reply builders. PIN needed for Behaviour and Weekly report."""
    if not parts:
        return _con(*_parent_menu_lines(learners, lang))
    language_option = str(len(PARENT_ACTIONS) + 1)
    if parts[0] == language_option:
        result = _change_language(db, phone, parts[1:], lambda new: _parent_menu_lines(learners, new))
        if isinstance(result, str):
            return result
        lang, rest = result
        return _parent_flow(db, phone, learners, rest, lang, defer)
    action = PARENT_ACTIONS.get(parts[0])
    if not action:
        return _end(t("invalid_choice", lang))
    steps = parts[1:]
    child = 1
    if len(learners) > 1:
        if not steps:
            lines = [t("choose_child", lang)]
            lines += [f"{i}. {l.name[:20]} ({l.classroom.name})" for i, l in enumerate(learners, start=1)]
            lines.append(t("nav_back", lang))
            return _con(*lines)
        if steps[0] == BACK:
            return _parent_flow(db, phone, learners, steps[1:], lang, defer)
        if not (steps[0].isdigit() and 1 <= int(steps[0]) <= len(learners)):
            return _end(t("invalid_choice", lang))
        child, steps = int(steps[0]), steps[1:]

    if action == "contact":
        if not steps:
            return _con(t("contact_prompt", lang))
        message = " ".join(steps).strip()
        if not message:
            return _end(t("contact_empty", lang))
        learner = learners[child - 1]
        db.add(ParentReply(learner_id=learner.id, phone=phone, code=None, raw_text=message[:300]))
        db.add(MessageLog(phone=phone, channel="ussd", command="contact", language=lang, inbound_text=message[:300],
                          reply_text=t("contact_sent", lang), status="ok", counted=True, learner_id=learner.id))
        db.commit()
        if defer is not None:
            defer(send_contact_message, learner.id, phone, message)
        else:
            send_contact_message(learner.id, phone, message, db)
        return _end(t("contact_sent", lang))

    pin = None
    if action in PIN_COMMANDS:
        if not steps:
            return _con(t("enter_pin", lang))
        pin = steps[0]
    log = run_query(
        db, phone, action, lang, child=child, pin=pin, channel="ussd",
        inbound_text=f"USSD {action.upper()}" + (" ****" if pin else ""),
    )
    return _end(log.reply_text or t("invalid_choice", lang))


# ---------- entry point ----------

def handle_ussd(
    db: Session, phone_number: str, text: str, defer: Callable | None = None, session_id: str | None = None
) -> str:
    phone = normalize_number(phone_number)
    teacher = db.scalar(select(Teacher).where(Teacher.phone == phone))
    children = guardian_learners(db, phone)
    if not teacher and not children:
        return f"END {t('not_registered')}"  # bilingual: language unknown

    parts = text.split("*") if text else []
    saved = phone_language(db, phone)
    if session_id and session_id in _LANGUAGE_SESSIONS and parts:
        parts = parts[1:]  # this session began with the language screen; drop that answer
    elif saved is None:
        if not parts:
            return _language_screen()
        chosen = LANGUAGE_CHOICES.get(parts[0])
        if not chosen:
            return f"END {_bilingual('invalid_choice')}"
        set_language(db, phone, chosen)
        _remember_language_session(session_id)
        parts = parts[1:]
    lang = normalize_language(phone_language(db, phone))

    if HOME in parts:  # "00" anywhere jumps back to the main menu
        last = len(parts) - 1 - parts[::-1].index(HOME)
        parts = parts[last + 1:]

    if not teacher:
        return _parent_flow(db, phone, children, parts, lang, defer)

    classes = sorted(teacher.classrooms, key=lambda room: room.name)
    if not classes:
        return _end(t("no_class", lang))
    is_parent = bool(children)
    parent_option, language_option = _teacher_option_numbers(is_parent)

    today = demo_today(db)
    if not parts:
        return _con(*_teacher_menu_lines(lang, is_parent))

    action = parts[0]
    if action == language_option:
        result = _change_language(db, phone, parts[1:], lambda new: _teacher_menu_lines(new, is_parent))
        if isinstance(result, str):
            return result
        _, rest = result
        return handle_ussd(db, phone, "*".join(rest), defer)
    if action == parent_option:
        return _parent_flow(db, phone, children, parts[1:], lang, defer)
    if action not in TEACHER_ACTIONS:
        return _end(t("invalid_choice", lang))

    if len(parts) == 1:
        return _class_selection(db, classes, TEACHER_ACTIONS[action], today, lang)
    if parts[1] == BACK:
        return handle_ussd(db, phone, "*".join(parts[2:]), defer)
    class_part = parts[1]
    if not (class_part.isdigit() and 1 <= int(class_part) <= len(classes)):
        return _end(t("invalid_choice", lang))
    classroom = classes[int(class_part) - 1]
    steps = parts[2:]

    if action == "1":
        return _attendance_flow(db, classroom, steps, today, lang, defer)
    if action == "2":
        return _summary(db, classroom, today, lang)
    if action == "3":
        return _at_risk_flow(db, classroom, steps, today, lang)
    if action == "4":
        return _behaviour_flow(db, teacher, classroom, steps, today, lang, defer)
    return _lookup_flow(db, classroom, steps, today, lang)


@router.post("/ussd", response_class=PlainTextResponse)
async def ussd_callback(
    request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> str:
    form = await request.form()
    return handle_ussd(
        db,
        str(form.get("phoneNumber", "")),
        str(form.get("text", "")),
        defer=background_tasks.add_task,
        session_id=str(form.get("sessionId", "")) or None,
    )
