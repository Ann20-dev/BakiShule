from datetime import date, datetime, timedelta

from app.models import AttendanceRecord, ClassRoom, Learner, ParentReply, School, Teacher
from app.services.risk import calculate_risk, recompute_learner, risk_level


def make_learner(db_session, name="Test Learner", phone="+254711000001"):
    school = School(name="Test School", county="Nairobi")
    suffix = len(db_session.identity_map)
    teacher = Teacher(name=f"Teacher {suffix}", phone=f"+254700{suffix:06d}")
    classroom = ClassRoom(name="5A", school=school, teacher=teacher)
    learner = Learner(
        name=name,
        roll_number=name,
        classroom=classroom,
        gender="female",
        guardian_name="Parent",
        guardian_phone=phone,
    )
    db_session.add(learner)
    db_session.flush()
    return learner


def add_records(db_session, learner, items):
    db_session.add_all(
        AttendanceRecord(learner_id=learner.id, date=day, present=present)
        for day, present in items
    )
    db_session.flush()


def test_consecutive_absence_rule(db_session):
    learner = make_learner(db_session)
    today = date(2026, 11, 25)  # Wednesday
    add_records(
        db_session,
        learner,
        [(today - timedelta(days=2), False), (today - timedelta(days=1), False), (today, False)],
    )
    score, reasons = calculate_risk(db_session, learner, today)
    assert score == 30
    assert "3 consecutive school-day absences" in reasons[0]


def test_recent_attendance_drop_rule(db_session):
    learner = make_learner(db_session)
    today = date(2026, 11, 25)
    records = [(today - timedelta(days=day), True) for day in range(14, 45)]
    records += [(today - timedelta(days=day), day % 2 == 0) for day in range(14)]
    add_records(db_session, learner, records)
    _, reasons = calculate_risk(db_session, learner, today)
    assert any("Attendance dropped" in reason for reason in reasons)


def test_weekday_pattern_rule(db_session):
    learner = make_learner(db_session)
    today = date(2026, 11, 25)
    mondays = [today - timedelta(days=offset) for offset in range(60) if (today - timedelta(days=offset)).weekday() == 0]
    add_records(
        db_session,
        learner,
        [(today - timedelta(days=offset), (today - timedelta(days=offset)).weekday() != 0)
         for offset in range(60) if (today - timedelta(days=offset)).weekday() < 5],
    )
    _, reasons = calculate_risk(db_session, learner, today)
    assert len(mondays) >= 3
    assert any("Monday absence pattern" in reason for reason in reasons)


def test_monthly_cluster_rule(db_session):
    learner = make_learner(db_session)
    dates = [date(2026, 10, day) for day in (5, 6, 7)] + [date(2026, 11, day) for day in (2, 3, 4)]
    add_records(db_session, learner, [(day, False) for day in dates])
    _, reasons = calculate_risk(db_session, learner, date(2026, 11, 25))
    assert any("Monthly absence clusters" in reason for reason in reasons)


def test_sibling_same_day_rule(db_session):
    learner = make_learner(db_session, phone="+254711000001")
    sibling = make_learner(db_session, name="Sibling", phone="+254711000001")
    days = [date(2026, 11, 2), date(2026, 11, 9)]
    add_records(db_session, learner, [(day, False) for day in days])
    add_records(db_session, sibling, [(day, False) for day in days])
    _, reasons = calculate_risk(db_session, learner, date(2026, 11, 25))
    assert any("Sibling absent on 2" in reason for reason in reasons)


def test_parent_fees_reply_rule(db_session):
    learner = make_learner(db_session)
    db_session.add(
        ParentReply(
            learner_id=learner.id,
            phone=learner.guardian_phone,
            code=2,
            raw_text="2",
            received_at=datetime(2026, 11, 20),
        )
    )
    score, reasons = calculate_risk(db_session, learner, date(2026, 11, 25))
    assert score == 15
    assert "Parent reported fee difficulty (+15)" in reasons


def test_risk_level_thresholds():
    assert [risk_level(s) for s in (0, 29, 30, 54, 55, 74, 75, 100)] == [
        "green", "green", "watch", "watch", "at_risk", "at_risk", "critical", "critical"
    ]


def test_watch_history_survives_same_day_recompute(db_session):
    learner = make_learner(db_session)
    today = date(2026, 11, 25)
    add_records(
        db_session,
        learner,
        [(today - timedelta(days=2), False), (today - timedelta(days=1), False), (today, False)],
    )
    snapshot, _ = recompute_learner(db_session, learner, today)
    assert snapshot.level == "watch"
    assert learner.ever_watch is True

    for record in db_session.query(AttendanceRecord).all():
        record.present = True
    snapshot, _ = recompute_learner(db_session, learner, today)
    assert snapshot.level == "green"
    assert learner.ever_watch is True
