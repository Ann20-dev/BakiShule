from datetime import datetime
from zoneinfo import ZoneInfo

from app.models import MessageLog
from app.services.sms_format import fit_sms, segment_count, sms_units
from app.services.weekly_reports import is_due, send_weekly_reports
from tests.test_parent_queries import PARENT, SINGLE_PARENT, build_school, fixed_today  # noqa: F401

NAIROBI = ZoneInfo("Africa/Nairobi")


def test_weekly_reports_skip_opted_out_guardians(db_session):
    _, _, kids = build_school(db_session)
    kids[1].sms_opt_out = True
    db_session.commit()
    delivered = []

    count = send_weekly_reports(db_session, deliver=lambda log_id, db: delivered.append(log_id))

    assert count == 2
    logs = db_session.query(MessageLog).filter_by(status="weekly_push").all()
    assert sorted(log.learner_id for log in logs) == sorted([kids[0].id, kids[2].id])
    assert sorted(delivered) == sorted(log.id for log in logs)
    assert all(log.reply_text.startswith("Weekly report -") and not log.counted for log in logs)
    assert {log.phone for log in logs} == {PARENT, SINGLE_PARENT}


def test_weekly_report_uses_guardian_language(db_session):
    build_school(db_session)
    from app.services.parent_queries import handle_sms_query

    handle_sms_query(db_session, SINGLE_PARENT, "LUGHA SW")  # parent chose Kiswahili
    send_weekly_reports(db_session, deliver=lambda log_id, db: None)
    log = db_session.query(MessageLog).filter_by(status="weekly_push", phone=SINGLE_PARENT).one()
    assert log.reply_text.startswith("Ripoti ya wiki - Chebet Kiprop, 5A:")
    english = db_session.query(MessageLog).filter_by(status="weekly_push", phone=PARENT).first()
    assert english.reply_text.startswith("Weekly report -")


def test_schedule_is_friday_1600_nairobi_once_per_week():
    friday_1559 = datetime(2026, 11, 27, 15, 59, tzinfo=NAIROBI)
    friday_1600 = datetime(2026, 11, 27, 16, 0, tzinfo=NAIROBI)
    thursday = datetime(2026, 11, 26, 17, 0, tzinfo=NAIROBI)
    assert is_due(friday_1559, None)[0] is False
    due, week = is_due(friday_1600, None)
    assert due is True and week == "2026-W48"
    assert is_due(friday_1600, "2026-W48")[0] is False  # already sent this week
    assert is_due(thursday, None)[0] is False


def test_segment_counting():
    assert sms_units("hello") == ("gsm7", 5)
    assert segment_count("a" * 160) == 1 and segment_count("a" * 161) == 2
    assert sms_units("⭐ ok")[0] == "ucs2"
    assert segment_count("⭐" + "a" * 69) == 1 and segment_count("⭐" + "a" * 70) == 2
    assert segment_count(fit_sms(["header", "x" * 400])) <= 2
    assert fit_sms(["keep", "y" * 400]) == "keep"
