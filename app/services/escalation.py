from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AttendanceRecord, ClassRoom, Intervention, Learner, ParentReply, RiskSnapshot, Teacher
from app.services.at_client import at_client

LEVEL_RANK = {"green": 0, "watch": 1, "at_risk": 2, "critical": 3}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _recent_duplicate(db: Session, learner: Learner, intervention_type: str, level: str) -> bool:
    recent = db.scalars(
        select(Intervention).where(
            Intervention.learner_id == learner.id,
            Intervention.type == intervention_type,
            Intervention.created_at >= _utcnow() - timedelta(days=7),
        )
    )
    return any(item.metadata_json.get("level") == level for item in recent)


def _log_send(
    db: Session,
    learner: Learner,
    intervention_type: str,
    recipient: str,
    message: str,
    metadata: dict | None = None,
) -> Intervention:
    try:
        response = at_client.send_sms(recipient, message)
    except Exception as error:
        db.add(
            Intervention(
                learner_id=learner.id,
                type=intervention_type,
                status="failed",
                metadata_json={
                    **(metadata or {}),
                    "recipient": recipient,
                    "message": message,
                    "error": f"{type(error).__name__}: {error}",
                },
            )
        )
        db.commit()
        raise
    intervention = Intervention(
        learner_id=learner.id,
        type=intervention_type,
        status=response.get("status", "submitted"),
        metadata_json={
            **(metadata or {}),
            "recipient": recipient,
            "message": message,
            "at_response": response,
        },
    )
    db.add(intervention)
    db.commit()
    return intervention


def _absence_days(db: Session, learner: Learner, as_of: date) -> int:
    record = db.scalar(
        select(AttendanceRecord)
        .where(
            AttendanceRecord.learner_id == learner.id,
            AttendanceRecord.date <= as_of,
        )
        .order_by(AttendanceRecord.date.desc())
        .limit(1)
    )
    if not record or record.present:
        return 0
    records = list(
        db.scalars(
            select(AttendanceRecord)
            .where(
                AttendanceRecord.learner_id == learner.id,
                AttendanceRecord.date <= as_of,
            )
            .order_by(AttendanceRecord.date.desc())
        )
    )
    days = 0
    previous_date: date | None = None
    for item in records:
        if not item.present:
            if previous_date:
                expected_previous = item.date + timedelta(days=1)
                while expected_previous.weekday() >= 5:
                    expected_previous += timedelta(days=1)
                if expected_previous != previous_date:
                    break
            days += 1
            previous_date = item.date
        elif previous_date:
            break
    return days


def _send_reward_if_due(
    db: Session,
    learner: Learner,
    as_of: date,
    previous_level: str | None,
) -> bool:
    start = as_of - timedelta(days=27)
    records = list(
        db.scalars(
            select(AttendanceRecord).where(
                AttendanceRecord.learner_id == learner.id,
                AttendanceRecord.date >= start,
                AttendanceRecord.date <= as_of,
            )
        )
    )
    school_days = sum((start + timedelta(days=offset)).weekday() < 5 for offset in range(28))
    if len(records) < min(20, school_days) or any(not item.present for item in records):
        return False
    was_watch_or_higher = db.scalar(
        select(RiskSnapshot.id)
        .where(
            RiskSnapshot.learner_id == learner.id,
            RiskSnapshot.level.in_(("watch", "at_risk", "critical")),
        )
        .limit(1)
    )
    if (
        not was_watch_or_higher
        and not learner.ever_watch
        and LEVEL_RANK.get(previous_level or "green", 0) < LEVEL_RANK["watch"]
    ):
        return False
    previous_reward = db.scalar(
        select(Intervention.id).where(
            Intervention.learner_id == learner.id,
            Intervention.type == "airtime_reward",
            Intervention.created_at >= _utcnow() - timedelta(days=28),
        ).limit(1)
    )
    if previous_reward:
        return False

    try:
        response = at_client.send_airtime(learner.guardian_phone, settings.airtime_reward_kes)
    except Exception as error:
        db.add(
            Intervention(
                learner_id=learner.id,
                type="airtime_reward",
                status="failed",
                metadata_json={
                    "amount": settings.airtime_reward_kes,
                    "currency": "KES",
                    "recipient": learner.guardian_phone,
                    "error": f"{type(error).__name__}: {error}",
                },
            )
        )
        db.commit()
        raise
    db.add(
        Intervention(
            learner_id=learner.id,
            type="airtime_reward",
            status=response.get("status", "submitted"),
            metadata_json={
                "amount": settings.airtime_reward_kes,
                "currency": "KES",
                "recipient": learner.guardian_phone,
                "at_response": response,
            },
        )
    )
    db.commit()
    congrats = f"Congratulations {learner.name.split()[0]}! You completed 4 weeks of full attendance. KES {settings.airtime_reward_kes} airtime is yours."
    _log_send(db, learner, "airtime_reward", learner.guardian_phone, congrats, {"level": "reward"})
    return True


def maybe_escalate(
    db: Session,
    learner: Learner,
    snapshot: RiskSnapshot,
    previous_level: str | None,
) -> None:
    previous_rank = LEVEL_RANK.get(previous_level, 0) if previous_level else 0
    current_rank = LEVEL_RANK[snapshot.level]
    if current_rank > previous_rank:
        if previous_rank < LEVEL_RANK["watch"] <= current_rank:
            level = "watch"
            if not learner.sms_opt_out and not _recent_duplicate(db, learner, "sms_checkin", level):
                days = _absence_days(db, learner, snapshot.date)
                if settings.default_language.lower() == "sw":
                    message = f"Tumekukosa {learner.name} kwa siku {days}. Kila kitu sawa? Jibu 1 Mgonjwa, 2 Ada, 3 Nyingine."
                else:
                    message = f"We missed {learner.name} on {days} days. Is everything okay? Reply 1 Sick, 2 Fees, 3 Other."
                _log_send(db, learner, "sms_checkin", learner.guardian_phone, message, {"level": level})
        if previous_rank < LEVEL_RANK["at_risk"] <= current_rank:
            level = "at_risk"
            if not _recent_duplicate(db, learner, "staff_alert", level):
                summary = "; ".join(snapshot.reasons[:2]) or "Attendance risk increased."
                reply = db.scalar(
                    select(ParentReply)
                    .where(ParentReply.learner_id == learner.id)
                    .order_by(ParentReply.received_at.desc())
                    .limit(1)
                )
                if reply:
                    summary += f" Parent reply: {reply.raw_text[:45]}"
                recipients = {learner.classroom.teacher.phone}
                head_teachers = db.scalars(
                    select(Teacher).join(Teacher.classrooms).where(
                        Teacher.role == "head_teacher",
                        ClassRoom.school_id == learner.classroom.school_id,
                    )
                )
                recipients.update(teacher.phone for teacher in head_teachers)
                message = f"At-risk: {learner.name} ({learner.classroom.name}). {summary}"[:155]
                for recipient in recipients:
                    _log_send(db, learner, "staff_alert", recipient, message, {"level": level})
        if previous_rank < LEVEL_RANK["critical"] <= current_rank:
            level = "critical"
            if not _recent_duplicate(db, learner, "sponsor_flag", level):
                db.add(
                    Intervention(
                        learner_id=learner.id,
                        type="sponsor_flag",
                        status="open",
                        metadata_json={
                            "level": level,
                            "score": snapshot.score,
                            "reasons": snapshot.reasons,
                            "need": "Fees and attendance support",
                        },
                    )
                )
                db.commit()

    if not learner.sms_opt_out:
        _send_reward_if_due(db, learner, snapshot.date, previous_level)
