from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AttendanceRecord, Learner, ParentReply, RiskSnapshot


def risk_level(score: int) -> str:
    if score >= 75:
        return "critical"
    if score >= 55:
        return "at_risk"
    if score >= 30:
        return "watch"
    return "green"


def calculate_risk(db: Session, learner: Learner, as_of: date | None = None) -> tuple[int, list[str]]:
    as_of = as_of or date.today()
    db.flush()
    start = as_of - timedelta(days=60)
    records = list(
        db.scalars(
            select(AttendanceRecord)
            .where(
                AttendanceRecord.learner_id == learner.id,
                AttendanceRecord.date >= start,
                AttendanceRecord.date <= as_of,
            )
            .order_by(AttendanceRecord.date)
        )
    )
    score = 0
    reasons: list[str] = []
    absences = [record.date for record in records if not record.present]

    # Consecutive means consecutive recorded school days; weekends are not attendance days.
    by_day = {record.date: record.present for record in records}
    latest_record = records[-1] if records else None
    streak = 0
    if latest_record and not latest_record.present:
        cursor = latest_record.date
        while by_day.get(cursor) is False:
            streak += 1
            cursor -= timedelta(days=1)
            while cursor.weekday() >= 5:
                cursor -= timedelta(days=1)
    if streak:
        points = min(streak * 10, 40)
        score += points
        reasons.append(f"{streak} consecutive school-day absences (+{points})")

    recent_start = as_of - timedelta(days=13)
    baseline_start = as_of - timedelta(days=60)
    recent = [r for r in records if r.date >= recent_start]
    baseline = [r for r in records if r.date < recent_start and r.date >= baseline_start]
    if recent and baseline:
        recent_rate = sum(r.present for r in recent) / len(recent)
        baseline_rate = sum(r.present for r in baseline) / len(baseline)
        drop = baseline_rate - recent_rate
        if drop >= 0.15:
            points = min(25, round(drop * 50))
            score += points
            reasons.append(
                f"Attendance dropped {drop:.0%} in the last 14 days vs 60-day baseline (+{points})"
            )

    weekdays: dict[int, list[bool]] = defaultdict(list)
    for record in records:
        weekdays[record.date.weekday()].append(record.present)
    average_absence_rate = sum(not r.present for r in records) / len(records) if records else 0
    patterned_days = [
        day for day, values in weekdays.items()
        if len(values) >= 3
        and sum(not present for present in values) / len(values) >= 0.5
        and sum(not present for present in values) / len(values) >= average_absence_rate + 0.2
    ]
    if patterned_days:
        score += 12
        day_name = date(2024, 1, 1) + timedelta(days=patterned_days[0])
        reasons.append(f"Recurring {day_name.strftime('%A')} absence pattern (+12)")

    by_month: Counter[str] = Counter(absence.strftime("%Y-%m") for absence in absences)
    months_with_cluster = sorted(month for month, count in by_month.items() if count >= 3)
    if len(months_with_cluster) >= 2:
        score += 15
        reasons.append(f"Monthly absence clusters in {', '.join(months_with_cluster[-2:])} (+15)")

    sibling_ids = list(
        db.scalars(
            select(Learner.id).where(
                Learner.guardian_phone == learner.guardian_phone,
                Learner.id != learner.id,
            )
        )
    )
    if sibling_ids and absences:
        sibling_absences = set(
            db.scalars(
                select(AttendanceRecord.date).where(
                    AttendanceRecord.learner_id.in_(sibling_ids),
                    AttendanceRecord.present.is_(False),
                    AttendanceRecord.date.in_(absences),
                )
            )
        )
        if len(sibling_absences) >= 2:
            score += 10
            reasons.append(f"Sibling absent on {len(sibling_absences)} of the same days (+10)")

    latest_fees_reply = db.scalar(
        select(ParentReply)
        .where(
            ParentReply.learner_id == learner.id,
            ParentReply.code == 2,
            ParentReply.received_at >= datetime.combine(as_of - timedelta(days=30), time.min),
        )
        .order_by(ParentReply.received_at.desc())
        .limit(1)
    )
    if latest_fees_reply:
        score += 15
        reasons.append("Parent reported fee difficulty (+15)")

    return min(score, 100), reasons


def recompute_learner(db: Session, learner: Learner, as_of: date | None = None) -> tuple[RiskSnapshot, str | None]:
    as_of = as_of or date.today()
    score, reasons = calculate_risk(db, learner, as_of)
    level = risk_level(score)
    if level in {"watch", "at_risk", "critical"}:
        learner.ever_watch = True
    existing = db.scalar(
        select(RiskSnapshot).where(
            RiskSnapshot.learner_id == learner.id,
            RiskSnapshot.date == as_of,
        )
    )
    previous_level = existing.level if existing else db.scalar(
        select(RiskSnapshot.level)
        .where(
            RiskSnapshot.learner_id == learner.id,
            RiskSnapshot.date < as_of,
        )
        .order_by(RiskSnapshot.date.desc())
        .limit(1)
    )
    if existing:
        existing.score = score
        existing.level = level
        existing.reasons = reasons
        snapshot = existing
    else:
        snapshot = RiskSnapshot(
            learner_id=learner.id,
            date=as_of,
            score=score,
            level=level,
            reasons=reasons,
        )
        db.add(snapshot)
    db.flush()
    return snapshot, previous_level


def recompute_all(
    db: Session,
    as_of: date | None = None,
    escalate_transitions: bool = True,
) -> list[RiskSnapshot]:
    learners = list(db.scalars(select(Learner).order_by(Learner.id)))
    updates = [
        (learner, *recompute_learner(db, learner, as_of))
        for learner in learners
    ]
    db.commit()
    if escalate_transitions:
        from app.services.escalation import maybe_escalate

        for learner, snapshot, previous_level in updates:
            maybe_escalate(db, learner, snapshot, previous_level)
    return [snapshot for _, snapshot, _ in updates]
