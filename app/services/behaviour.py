from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BehaviourLog, Learner, Teacher
from app.school_config import BEHAVIOUR_CODES, BEHAVIOUR_RISK


def log_behaviour(
    db: Session,
    learner: Learner,
    teacher: Teacher | None,
    code: int,
    on_date: date,
    subject: str | None = None,
) -> BehaviourLog:
    if code not in BEHAVIOUR_CODES:
        raise ValueError(f"Unknown behaviour code {code}")
    entry = BehaviourLog(
        learner_id=learner.id,
        teacher_id=teacher.id if teacher else None,
        code=code,
        sentiment=BEHAVIOUR_CODES[code]["sentiment"],
        subject=subject,
        date=on_date,
    )
    db.add(entry)
    db.flush()
    return entry


def behaviour_logs(
    db: Session, learner_id: int, start: date | None = None, end: date | None = None, limit: int | None = None
) -> list[BehaviourLog]:
    query = select(BehaviourLog).where(BehaviourLog.learner_id == learner_id)
    if start:
        query = query.where(BehaviourLog.date >= start)
    if end:
        query = query.where(BehaviourLog.date <= end)
    query = query.order_by(BehaviourLog.date.desc(), BehaviourLog.id.desc())
    if limit:
        query = query.limit(limit)
    return list(db.scalars(query))


def recent_concern_count(db: Session, learner_id: int, as_of: date) -> int:
    start = as_of - timedelta(days=BEHAVIOUR_RISK["window_days"] - 1)
    return sum(log.sentiment == "concern" for log in behaviour_logs(db, learner_id, start, as_of))
