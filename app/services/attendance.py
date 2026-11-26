from collections.abc import Callable
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AttendanceRecord, ClassRoom, Learner, RiskSnapshot
from app.services.clock import demo_today
from app.services.escalation import maybe_escalate
from app.services.risk import recompute_learner


def save_class_attendance(
    db: Session,
    classroom: ClassRoom,
    absent_roll_numbers: set[str],
    on_date: date | None = None,
    defer: Callable | None = None,
) -> int:
    """Save attendance and recompute risk.

    Escalations (SMS/airtime) run inline by default. Pass `defer` (e.g. FastAPI's
    BackgroundTasks.add_task) to send them after the response, so USSD stays under AT's 3s limit.
    """
    on_date = on_date or demo_today(db)
    absent_roll_numbers = {value.strip() for value in absent_roll_numbers}
    learners = list(classroom.learners)
    if absent_roll_numbers - {learner.roll_number for learner in learners}:
        raise ValueError("Unknown roll number for this class")

    for learner in learners:
        record = db.scalar(
            select(AttendanceRecord).where(
                AttendanceRecord.learner_id == learner.id,
                AttendanceRecord.date == on_date,
            )
        )
        present = learner.roll_number not in absent_roll_numbers
        if record:
            record.present = present
        else:
            db.add(
                AttendanceRecord(
                    learner_id=learner.id,
                    date=on_date,
                    present=present,
                )
            )
    db.flush()
    risk_updates = [
        (learner, *recompute_learner(db, learner, on_date))
        for learner in learners
    ]
    db.commit()
    if defer is not None:
        defer(
            run_escalations,
            [(learner.id, snapshot.id, previous_level) for learner, snapshot, previous_level in risk_updates],
        )
        return len(learners)
    for learner, snapshot, previous_level in risk_updates:
        maybe_escalate(db, learner, snapshot, previous_level)
    db.commit()
    return len(learners)


def run_escalations(updates: list[tuple[int, int, str | None]]) -> None:
    """Background job: send any SMS/airtime that the new risk levels call for."""
    from app.db import SessionLocal

    with SessionLocal() as db:
        for learner_id, snapshot_id, previous_level in updates:
            learner, snapshot = db.get(Learner, learner_id), db.get(RiskSnapshot, snapshot_id)
            if learner and snapshot:
                try:
                    maybe_escalate(db, learner, snapshot, previous_level)
                except Exception:  # one failed send must not stop the rest
                    import logging

                    logging.getLogger(__name__).exception("Escalation failed for learner %s", learner_id)
        db.commit()
