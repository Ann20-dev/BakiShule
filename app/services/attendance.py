from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AttendanceRecord, ClassRoom
from app.services.clock import demo_today
from app.services.escalation import maybe_escalate
from app.services.risk import recompute_learner


def save_class_attendance(
    db: Session,
    classroom: ClassRoom,
    absent_roll_numbers: set[str],
    on_date: date | None = None,
) -> int:
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
    for learner, snapshot, previous_level in risk_updates:
        maybe_escalate(db, learner, snapshot, previous_level)
    db.commit()
    return len(learners)
