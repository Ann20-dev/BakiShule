"""Incoming SMS (check-in replies, parent commands) and delivery reports. Text: app/messages.py."""
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.messages import t
from app.models import Intervention, Learner, MessageLog, ParentReply, utc_now_naive
from app.services.clock import demo_today
from app.services.escalation import _log_send, maybe_escalate
from app.services.language import guardian_language, reply_language, teacher_language
from app.config import settings
from app.services.ai_chat import ai_enabled, chat_reply
from app.services.parent_queries import (
    START_WORDS, STOP_WORDS, deliver_message_log, handle_sms_query, language_prompt_if_needed, mask_pins,
    rate_limit_state,
)
from app.services.sms_format import fit_sms
from app.services.phone import normalize_number
from app.services.risk import recompute_learner

router = APIRouter()


def _log_checkin(
    db: Session, learners: list[Learner], sender: str, text: str, command: str, lang: str
) -> MessageLog:
    """Record a check-in reply (1/2/3/STOP/START/free text) for the dashboard's Parent queries panel."""
    log = MessageLog(
        phone=sender, channel="sms", command=command, language=lang, inbound_text=text,
        status="checkin", learner_id=learners[0].id,
    )
    db.add(log)
    db.flush()
    return log


def _acknowledge(
    db: Session, learners: list[Learner], sender: str, key, lang: str, log: MessageLog | None = None
) -> None:
    """Send the parent one confirmation SMS (never after STOP)."""
    names = " & ".join(learner.name for learner in learners[:3])
    message = t(f"ack_{str(key).lower()}", lang, names=names)[:160]
    try:
        intervention = _log_send(db, learners[0], "parent_ack", sender, message, {"reply": str(key)})
        status = intervention.status
    except Exception:  # the parent's reply is already saved; a failed ack must not lose it
        status = "failed"
    if log is not None:
        log.reply_text = message
        log.delivery_status = status
        db.commit()


def _teacher_message(db: Session, learner: Learner, key: str, reason: str, **params) -> None:
    """Alert the class teacher in the teacher's own language."""
    teacher = learner.classroom.teacher
    message = t(key, teacher_language(teacher), name=learner.name, **params)
    _log_send(db, learner, "staff_alert", teacher.phone, message[:155], {"category": reason})


def handle_inbound_sms(db: Session, sender: str, raw_text: str) -> int:
    """Check-in replies from a registered guardian: 1/2/3, STOP/ACHA, START/ANZA, or free text.

    STOP/ACHA/START/ANZA reply in the language of that word; 1/2/3 and free text use the saved
    preference (default English)."""
    text = raw_text.strip()
    normalized = text.upper()
    learners = list(db.scalars(select(Learner).where(Learner.guardian_phone == sender)))
    if not learners:
        return 0
    saved_lang = reply_language(guardian_language(db, sender))

    if normalized in STOP_WORDS or normalized in START_WORDS:
        stopping = normalized in STOP_WORDS
        lang = STOP_WORDS.get(normalized) or START_WORDS[normalized]
        log = _log_checkin(db, learners, sender, text, "stop" if stopping else "start", lang)
        for learner in learners:
            learner.sms_opt_out = stopping
            db.add(ParentReply(learner_id=learner.id, phone=sender, code=None, raw_text=text))
        db.commit()
        if not stopping:
            _acknowledge(db, learners, sender, "START", lang, log)
        return len(learners)

    code = int(text) if text in {"1", "2", "3"} else None
    safe_text = mask_pins(text)  # a PIN typed inside a sentence is never stored or forwarded
    if code is None:
        handled = _ai_chat(db, learners, sender, text, safe_text, saved_lang)
        if handled is not None:
            return handled

    log = _log_checkin(db, learners, sender, safe_text, f"reply_{text}" if code else "free_text", saved_lang)
    _apply_reply(db, learners, sender, code, safe_text)
    if not any(learner.sms_opt_out for learner in learners):
        _acknowledge(db, learners, sender, code or 3, saved_lang, log)
    return len(learners)


def _apply_reply(db: Session, learners: list[Learner], sender: str, code: int | None, text: str) -> None:
    """Record a check-in reply and act on it: 1 sick -> teacher alert, 2 fees -> risk + sponsor flag,
    anything else -> forwarded to the teacher."""
    for learner in learners:
        db.add(ParentReply(learner_id=learner.id, phone=sender, code=code, raw_text=text))
    db.flush()
    for learner in learners:
        if code == 1:
            _teacher_message(db, learner, "teacher_parent_sick", "parent_sick_reply")
        elif code == 2:
            snapshot, previous_level = recompute_learner(db, learner, demo_today(db))
            maybe_escalate(db, learner, snapshot, previous_level)
            recent_flag = db.scalars(
                select(Intervention).where(
                    Intervention.learner_id == learner.id,
                    Intervention.type == "sponsor_flag",
                    Intervention.created_at >= utc_now_naive() - timedelta(days=7),
                )
            )
            if not any(item.metadata_json.get("reason") == "parent_fees" for item in recent_flag):
                db.add(
                    Intervention(
                        learner_id=learner.id,
                        type="sponsor_flag",
                        status="open",
                        metadata_json={
                            "reason": "parent_fees",
                            "need": "Fees support requested by guardian",
                            "parent_reply": text,
                        },
                    )
                )
                db.commit()
        else:
            _teacher_message(db, learner, "teacher_parent_reply", "parent_other_reply", text=text[:90])
    db.commit()


AI_INTENT_CODES = {"report_sick": 1, "report_fees": 2, "message_for_teacher": 3}


def _ai_chat(
    db: Session, learners: list[Learner], sender: str, text: str, safe_text: str, saved_lang: str
) -> int | None:
    """Answer a free-text SMS like a chat, using the child's real data. Returns None to fall back
    to the plain check-in flow (AI off, failed, or not configured)."""
    if not ai_enabled():
        return None
    state = rate_limit_state(db, sender)
    if state != "ok":
        log = _log_checkin(db, learners, sender, safe_text, "chat", saved_lang)
        log.status = "rate_limited" if state == "notify" else "rate_limited_silent"
        if state == "notify":
            log.reply_text = t("rate_limited", saved_lang, limit=settings.parent_daily_query_limit)
            log.delivery_status = "pending"
        db.commit()
        if log.reply_text:
            deliver_message_log(log.id, db)
        return len(learners)

    result = chat_reply(db, sender, learners, text, demo_today(db), saved_lang)
    if result is None:
        return None
    targets = learners
    if 1 <= result.child_number <= len(learners):
        targets = [learners[result.child_number - 1]]
    code = AI_INTENT_CODES.get(result.intent)
    if code:
        _apply_reply(db, targets, sender, code, safe_text)  # same actions as replies 1 / 2 / 3
    else:
        for learner in targets:
            db.add(ParentReply(learner_id=learner.id, phone=sender, code=None, raw_text=safe_text))
    log = MessageLog(
        phone=sender, channel="sms", command=f"chat_{result.intent}", language=result.language,
        inbound_text=safe_text, reply_text=fit_sms([result.reply], result.language), status="ok",
        counted=True, learner_id=targets[0].id, delivery_status="pending",
    )
    db.add(log)
    db.commit()
    deliver_message_log(log.id, db)
    return len(learners)


def handle_delivery_report(db: Session, message_id: str, status: str, failure_reason: str = "") -> bool:
    """Update the intervention whose SMS has this AT messageId. Returns True if found."""
    if not message_id:
        return False
    candidates = db.scalars(
        select(Intervention)
        .where(Intervention.created_at >= utc_now_naive() - timedelta(days=7))
        .order_by(Intervention.created_at.desc())
    )
    for intervention in candidates:
        metadata = intervention.metadata_json or {}
        if metadata.get("message_id") == message_id:
            intervention.status = "delivered" if status == "Success" else status.lower()
            intervention.metadata_json = {
                **metadata,
                "delivery_status": status,
                "failure_reason": failure_reason or None,
                "delivery_updated_at": utc_now_naive().isoformat(timespec="seconds"),
            }
            db.commit()
            return True
    return False


@router.post("/sms/delivery")
async def delivery_report_callback(request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    """AT delivery report: form fields id, status, phoneNumber, networkCode, failureReason, retryCount."""
    form = await request.form()
    found = handle_delivery_report(
        db,
        str(form.get("id", "")),
        str(form.get("status", "")),
        str(form.get("failureReason", "")),
    )
    return {"status": "ok" if found else "unknown_message"}


@router.post("/sms/inbound")
async def inbound_sms_callback(
    request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> dict[str, str]:
    """AT incoming SMS. Answers immediately; replies are sent in the background."""
    form = await request.form()
    sender = normalize_number(str(form.get("from", "")))
    raw_text = str(form.get("text", ""))
    welcome = language_prompt_if_needed(db, sender, raw_text)  # first contact, no language yet
    if welcome:
        background_tasks.add_task(deliver_message_log, welcome.id)
    log = handle_sms_query(db, sender, raw_text)  # commands + unknown numbers
    if log is None:
        background_tasks.add_task(_checkin_job, sender, raw_text)  # 1/2/3, STOP/ACHA, START/ANZA, free text
    elif log.reply_text:
        background_tasks.add_task(deliver_message_log, log.id)
    return {"status": "ok"}


def _checkin_job(sender: str, raw_text: str) -> None:
    from app.db import SessionLocal

    with SessionLocal() as db:
        handle_inbound_sms(db, sender, raw_text)
