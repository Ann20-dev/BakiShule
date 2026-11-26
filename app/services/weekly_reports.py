"""Weekly REPORT push: Fridays 16:00 Africa/Nairobi to every guardian who hasn't opted out."""
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import DemoState, GuardianAccount, Learner, MessageLog
from app.services.clock import demo_today
from app.services.language import reply_language
from app.services.parent_queries import build_report, deliver_message_log, render_sms

logger = logging.getLogger(__name__)

SEND_WEEKDAY = 4  # Friday
SEND_HOUR = 16
STATE_KEY = "weekly_report_week"


def send_weekly_reports(db: Session, deliver=deliver_message_log) -> int:
    """Build and send one REPORT per learner (DRY_RUN is respected by the SMS client)."""
    today = demo_today(db)
    languages = {account.phone: account.language for account in db.scalars(select(GuardianAccount))}
    learners = list(db.scalars(select(Learner).where(Learner.sms_opt_out.is_(False)).order_by(Learner.id)))
    log_ids = []
    for learner in learners:
        lang = reply_language(languages.get(learner.guardian_phone))  # saved preference, default English
        log = MessageLog(
            phone=learner.guardian_phone,
            channel="sms",
            command="report",
            language=lang,
            inbound_text=None,
            reply_text=render_sms(build_report(db, learner, today, lang), lang),
            status="weekly_push",
            counted=False,
            learner_id=learner.id,
            delivery_status="pending",
        )
        db.add(log)
        db.flush()
        log_ids.append(log.id)
    db.commit()
    for log_id in log_ids:
        deliver(log_id, db)
    return len(log_ids)


def run_weekly_reports_job() -> int:
    from app.db import SessionLocal

    with SessionLocal() as db:
        count = send_weekly_reports(db)
    logger.info("Weekly reports sent: %s", count)
    return count


def is_due(now: datetime, last_sent_week: str | None) -> tuple[bool, str]:
    week_key = f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"
    due = now.weekday() == SEND_WEEKDAY and now.hour >= SEND_HOUR and last_sent_week != week_key
    return due, week_key


async def weekly_report_scheduler(poll_seconds: int = 60) -> None:
    """Checks once a minute; sends at most once per ISO week."""
    from app.db import SessionLocal

    zone = ZoneInfo(settings.timezone)
    while True:
        try:
            with SessionLocal() as db:
                state = db.get(DemoState, STATE_KEY)
                due, week_key = is_due(datetime.now(zone), state.value if state else None)
                if due:
                    if state:
                        state.value = week_key
                    else:
                        db.add(DemoState(key=STATE_KEY, value=week_key))
                    db.commit()
            if due:
                await asyncio.to_thread(run_weekly_reports_job)
        except Exception:
            logger.exception("Weekly report scheduler error")
        await asyncio.sleep(poll_seconds)
