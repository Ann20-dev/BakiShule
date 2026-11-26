from app.models import ClassRoom, Intervention, Learner, ParentReply, School, Teacher
from app.routes.sms import handle_inbound_sms


def create_family(db_session):
    school = School(name="Test School", county="Nairobi")
    teacher = Teacher(name="Teacher", phone="+254700123456")
    classroom = ClassRoom(name="5A", school=school, teacher=teacher)
    family = [
        Learner(
            name=f"Child {number}",
            roll_number=f"{number:02d}",
            classroom=classroom,
            gender="female",
            guardian_name="Parent",
            guardian_phone="+254711123456",
        )
        for number in (1, 2)
    ]
    db_session.add_all([school, teacher, classroom, *family])
    db_session.flush()
    return family


def test_parent_fees_reply_updates_all_siblings_and_flags(db_session):
    family = create_family(db_session)

    assert handle_inbound_sms(db_session, "+254711123456", "2") == 2

    assert db_session.query(ParentReply).count() == 2
    assert all(reply.code == 2 for reply in db_session.query(ParentReply).all())
    assert db_session.query(Intervention).filter_by(type="sponsor_flag").count() == 2


def test_sick_reply_notifies_teacher_and_logs_outbound(db_session, monkeypatch):
    family = create_family(db_session)
    sent = []
    monkeypatch.setattr("app.services.escalation.at_client.send_sms", lambda phone, text: sent.append((phone, text)) or {"status": "mocked"})

    handle_inbound_sms(db_session, family[0].guardian_phone, "1")

    teacher_msgs = [text for phone, text in sent if phone == "+254700123456"]
    parent_msgs = [text for phone, text in sent if phone == family[0].guardian_phone]
    assert len(teacher_msgs) == 2
    assert parent_msgs == ["Thank you. Get well soon, Child 1 & Child 2! The class teacher has been informed."]
    assert db_session.query(Intervention).filter_by(type="staff_alert").count() == 2
    assert db_session.query(Intervention).filter_by(type="parent_ack").count() == 1


def test_stop_persists_opt_out_without_sending_sms(db_session, monkeypatch):
    family = create_family(db_session)
    monkeypatch.setattr(
        "app.services.escalation.at_client.send_sms",
        lambda *args: (_ for _ in ()).throw(AssertionError("STOP must not send")),
    )

    handle_inbound_sms(db_session, family[0].guardian_phone, "STOP")

    assert all(learner.sms_opt_out for learner in family)
    assert db_session.query(ParentReply).filter_by(raw_text="STOP").count() == 2


def test_fees_reply_gets_acknowledgement(db_session, monkeypatch):
    family = create_family(db_session)
    sent = []
    monkeypatch.setattr("app.services.escalation.at_client.send_sms", lambda phone, text: sent.append((phone, text)) or {"status": "mocked"})

    handle_inbound_sms(db_session, family[0].guardian_phone, "2")

    assert (family[0].guardian_phone, "Thank you for telling us. The school will contact you about fee support for Child 1 & Child 2.") in sent


def test_delivery_report_updates_matching_sms(db_session, monkeypatch):
    from app.routes.sms import handle_delivery_report

    family = create_family(db_session)
    monkeypatch.setattr(
        "app.services.escalation.at_client.send_sms",
        lambda phone, text: {"status": "sent", "message_id": "ATXid_abc"},
    )
    handle_inbound_sms(db_session, family[0].guardian_phone, "3")

    assert handle_delivery_report(db_session, "ATXid_abc", "Success") is True
    ack = db_session.query(Intervention).filter_by(type="parent_ack").one()
    assert ack.status == "delivered"
    assert handle_delivery_report(db_session, "ATXid_missing", "Failed") is False


def test_delivery_report_records_failure_reason(db_session, monkeypatch):
    from app.routes.sms import handle_delivery_report

    family = create_family(db_session)
    monkeypatch.setattr(
        "app.services.escalation.at_client.send_sms",
        lambda phone, text: {"status": "sent", "message_id": "ATXid_x"},
    )
    handle_inbound_sms(db_session, family[0].guardian_phone, "3")
    handle_delivery_report(db_session, "ATXid_x", "Failed", "AbsentSubscriber")
    ack = db_session.query(Intervention).filter_by(type="parent_ack").one()
    assert ack.status == "failed"
    assert ack.metadata_json["failure_reason"] == "AbsentSubscriber"
