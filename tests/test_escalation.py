from datetime import date, datetime, timedelta

from app.models import AttendanceRecord, ClassRoom, Intervention, Learner, RiskSnapshot, School, Teacher, utc_now_naive
from app.services import escalation
from app.services.risk import recompute_all


def build_learner(db_session):
    school = School(name="Test School", county="Nairobi")
    teacher = Teacher(name="Teacher", phone="+254700123456")
    head = Teacher(name="Head", phone="+254700123457", role="head_teacher")
    classroom = ClassRoom(name="5A", school=school, teacher=teacher)
    head_class = ClassRoom(name="6A", school=school, teacher=head)
    learner = Learner(
        name="Asha Njeri",
        roll_number="01",
        classroom=classroom,
        gender="female",
        guardian_name="Parent",
        guardian_phone="+254711123456",
    )
    db_session.add_all([school, teacher, head, classroom, head_class, learner])
    db_session.flush()
    return learner


def snapshot(learner, level, on_date):
    return RiskSnapshot(
        learner_id=learner.id,
        date=on_date,
        score={"green": 10, "watch": 35, "at_risk": 60, "critical": 80}[level],
        level=level,
        reasons=["Recent attendance drop"],
    )


def test_watch_transition_sends_parent_checkin_and_logs_response(db_session, monkeypatch):
    learner = build_learner(db_session)
    yesterday = date.today() - timedelta(days=1)
    current = date.today()
    db_session.add(snapshot(learner, "green", yesterday))
    db_session.flush()
    calls = []
    monkeypatch.setattr(escalation.at_client, "send_sms", lambda phone, text: calls.append((phone, text)) or {"status": "mocked"})

    escalation.maybe_escalate(db_session, learner, snapshot(learner, "watch", current), "green")

    assert len(calls) == 1
    assert calls[0][0] == learner.guardian_phone
    intervention = db_session.query(Intervention).one()
    assert intervention.type == "sms_checkin"
    assert intervention.metadata_json["at_response"]["status"] == "mocked"


def test_sdk_sms_response_without_top_level_status_is_logged_as_submitted(
    db_session, monkeypatch
):
    learner = build_learner(db_session)
    response = {
        "SMSMessageData": {
            "Message": "Sent to 1/1",
            "Recipients": [
                {
                    "number": learner.guardian_phone,
                    "status": "Success",
                    "statusCode": 101,
                }
            ],
        }
    }
    monkeypatch.setattr(
        escalation.at_client, "send_sms", lambda phone, text: response
    )

    escalation.maybe_escalate(
        db_session, learner, snapshot(learner, "watch", date.today()), "green"
    )

    intervention = db_session.query(Intervention).one()
    assert intervention.status == "submitted"
    assert intervention.metadata_json["at_response"] == response


def test_sdk_airtime_response_without_top_level_status_is_logged_as_submitted(
    db_session, monkeypatch
):
    learner = build_learner(db_session)
    today = date.today()
    start = today - timedelta(days=27)
    db_session.add_all(
        AttendanceRecord(learner_id=learner.id, date=start + timedelta(days=offset), present=True)
        for offset in range(28)
        if (start + timedelta(days=offset)).weekday() < 5
    )
    db_session.flush()
    response = {
        "errorMessage": "None",
        "numSent": 1,
        "responses": [{"phoneNumber": learner.guardian_phone, "status": "Sent"}],
    }
    monkeypatch.setattr(escalation.at_client, "send_airtime", lambda *args: response)
    monkeypatch.setattr(
        escalation.at_client, "send_sms", lambda *args: {"status": "mocked"}
    )

    escalation.maybe_escalate(db_session, learner, snapshot(learner, "green", today), "at_risk")

    airtime_intervention = next(
        item
        for item in db_session.query(Intervention).filter_by(type="airtime_reward")
        if item.metadata_json.get("at_response") == response
    )
    assert airtime_intervention.status == "submitted"


def test_same_level_duplicate_is_suppressed_for_seven_days(db_session, monkeypatch):
    learner = build_learner(db_session)
    db_session.add(
        Intervention(
            learner_id=learner.id,
            type="sms_checkin",
            status="sent",
            created_at=utc_now_naive() - timedelta(days=2),
            metadata_json={"level": "watch"},
        )
    )
    db_session.flush()
    calls = []
    monkeypatch.setattr(escalation.at_client, "send_sms", lambda phone, text: calls.append(phone) or {})

    escalation.maybe_escalate(db_session, learner, snapshot(learner, "watch", date.today()), "green")

    assert calls == []
    assert db_session.query(Intervention).count() == 1


def test_at_risk_transition_alerts_teacher_and_head_teacher(db_session, monkeypatch):
    learner = build_learner(db_session)
    calls = []
    monkeypatch.setattr(escalation.at_client, "send_sms", lambda phone, text: calls.append(phone) or {"status": "mocked"})

    escalation.maybe_escalate(db_session, learner, snapshot(learner, "at_risk", date.today()), "watch")

    assert set(calls) == {"+254700123456", "+254700123457"}
    assert db_session.query(Intervention).count() == 2
    assert all(item.type == "staff_alert" for item in db_session.query(Intervention).all())


def test_critical_transition_creates_sponsor_flag(db_session, monkeypatch):
    learner = build_learner(db_session)
    monkeypatch.setattr(escalation.at_client, "send_sms", lambda *args: {})

    escalation.maybe_escalate(db_session, learner, snapshot(learner, "critical", date.today()), "at_risk")

    intervention = db_session.query(Intervention).one()
    assert intervention.type == "sponsor_flag"
    assert intervention.status == "open"


def test_direct_critical_jump_crosses_all_escalation_tiers(db_session, monkeypatch):
    learner = build_learner(db_session)
    calls = []
    monkeypatch.setattr(escalation.at_client, "send_sms", lambda phone, text: calls.append(phone) or {"status": "mocked"})

    escalation.maybe_escalate(db_session, learner, snapshot(learner, "critical", date.today()), "green")

    assert set(calls) == {learner.guardian_phone, "+254700123456", "+254700123457"}
    assert db_session.query(Intervention).filter_by(type="sponsor_flag").count() == 1


def test_bulk_recompute_escalates_new_watch_transition(db_session, monkeypatch):
    learner = build_learner(db_session)
    today = date.today()
    db_session.add(RiskSnapshot(learner_id=learner.id, date=today - timedelta(days=1), score=0, level="green", reasons=[]))
    db_session.add_all(
        AttendanceRecord(learner_id=learner.id, date=today - timedelta(days=offset), present=False)
        for offset in range(3)
    )
    db_session.commit()
    sent = []
    monkeypatch.setattr(escalation.at_client, "send_sms", lambda phone, text: sent.append((phone, text)) or {"status": "mocked"})

    snapshots = recompute_all(db_session, today)

    assert snapshots[0].level == "watch"
    assert [phone for phone, _ in sent] == [learner.guardian_phone]
    assert db_session.query(Intervention).filter_by(type="sms_checkin").count() == 1


def test_seed_recompute_can_suppress_interventions(db_session, monkeypatch):
    learner = build_learner(db_session)
    today = date.today()
    db_session.add_all(
        AttendanceRecord(learner_id=learner.id, date=today - timedelta(days=offset), present=False)
        for offset in range(3)
    )
    db_session.commit()
    monkeypatch.setattr(
        escalation.at_client,
        "send_sms",
        lambda *args: (_ for _ in ()).throw(AssertionError("seed recompute must not send")),
    )

    snapshots = recompute_all(db_session, today, escalate_transitions=False)

    assert snapshots[0].level == "watch"
    assert db_session.query(Intervention).count() == 0


def test_full_four_week_streak_rewards_previously_at_risk_learner(db_session, monkeypatch):
    learner = build_learner(db_session)
    today = date.today()
    start = today - timedelta(days=27)
    db_session.add_all(
        AttendanceRecord(learner_id=learner.id, date=start + timedelta(days=offset), present=True)
        for offset in range(28)
        if (start + timedelta(days=offset)).weekday() < 5
    )
    db_session.flush()
    airtime = []
    messages = []
    monkeypatch.setattr(escalation.at_client, "send_airtime", lambda *args: airtime.append(args) or {"status": "mocked"})
    monkeypatch.setattr(escalation.at_client, "send_sms", lambda *args: messages.append(args) or {"status": "mocked"})

    escalation.maybe_escalate(db_session, learner, snapshot(learner, "green", today), "at_risk")

    assert len(airtime) == 1
    assert len(messages) == 1
    assert db_session.query(Intervention).filter_by(type="airtime_reward").count() == 2
