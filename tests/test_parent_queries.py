from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models import (
    AttendanceRecord, BehaviourLog, ClassRoom, GuardianAccount, Learner, MessageLog, RiskSnapshot, School, Teacher,
    utc_now_naive,
)
from app.routes.ussd import handle_ussd
from app.services import parent_queries as pq
from app.services.behaviour import log_behaviour
from app.services.risk import calculate_risk
from app.services.sms_format import segment_count, sms_units

PARENT = "+254711123456"
SINGLE_PARENT = "+254722000111"
PIN = "4821"
TODAY = date(2026, 11, 25)  # a Wednesday, so results don't depend on the day tests run


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    for target in ("app.services.parent_queries.demo_today", "app.routes.ussd.demo_today",
                   "app.services.weekly_reports.demo_today", "app.routes.sms.demo_today"):
        monkeypatch.setattr(target, lambda db: TODAY)


def build_school(db_session):
    """Two siblings with PARENT, one only-child with SINGLE_PARENT, attendance this week + last week."""
    school = School(name="Test School", county="Nairobi")
    teacher = Teacher(name="Jane Otieno", phone="+254700123456", language="en")
    classroom = ClassRoom(name="5A", school=school, teacher=teacher)
    kids = [
        Learner(name="Asha Njeri", roll_number="01", classroom=classroom, gender="female",
                guardian_name="Mama Asha", guardian_phone=PARENT),
        Learner(name="Baraka Otieno", roll_number="02", classroom=classroom, gender="male",
                guardian_name="Mama Asha", guardian_phone=PARENT),
        Learner(name="Chebet Kiprop", roll_number="03", classroom=classroom, gender="female",
                guardian_name="Baba Chebet", guardian_phone=SINGLE_PARENT),
    ]
    db_session.add_all([school, teacher, classroom, *kids])
    db_session.flush()
    for offset in range(0, 15):
        day = TODAY - timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        for kid in kids:
            # Chebet misses today; everyone else is present
            db_session.add(AttendanceRecord(learner_id=kid.id, date=day, present=not (kid is kids[2] and offset == 0)))
    pq.set_pin(db_session, PARENT, PIN).language = "en"
    pq.set_pin(db_session, SINGLE_PARENT, PIN).language = "en"
    db_session.commit()
    return teacher, classroom, kids


def ask(db_session, phone, text):
    return pq.handle_sms_query(db_session, phone, text)


# ---------- parsing ----------

@pytest.mark.parametrize(
    "text, command, lang, child, pin",
    [
        ("STATUS", "status", "en", None, None),
        ("status", "status", "en", None, None),
        ("  Status 2 ", "status", "en", 2, None),
        ("HALI", "status", "sw", None, None),
        ("att", "att", "en", None, None),
        ("Mahudhurio 1", "att", "sw", 1, None),
        ("BEHAVIOUR 4821", "behaviour", "en", None, "4821"),
        ("behavior 4821", "behaviour", "en", None, "4821"),
        ("tabia 2 4821", "behaviour", "sw", 2, "4821"),
        ("REPORT 4821 2", "report", "en", 2, "4821"),
        ("Ripoti 4821", "report", "sw", None, "4821"),
        ("MENU", "menu", "en", None, None),
        ("help", "menu", "en", None, None),
        ("msaada", "menu", "sw", None, None),
    ],
)
def test_parse_command(text, command, lang, child, pin):
    parsed = pq.parse_command(text)
    assert (parsed.command, parsed.lang, parsed.child, parsed.pin) == (command, lang, child, pin)


@pytest.mark.parametrize("text", ["1", "2", "STOP", "START", "hello teacher", "", "STATUSS"])
def test_non_commands_are_not_parsed(text):
    assert pq.parse_command(text) is None


# ---------- identity & unknown numbers ----------

def test_unknown_number_gets_generic_reply_without_learner_data(db_session):
    build_school(db_session)
    log = ask(db_session, "+254799999999", "STATUS")
    assert log.status == "unknown_number"
    assert "not registered" in log.reply_text
    assert "Asha" not in log.reply_text and "Chebet" not in log.reply_text
    assert log.learner_id is None


def test_unknown_number_free_text_also_gets_generic_reply_but_stop_is_silent(db_session):
    build_school(db_session)
    assert ask(db_session, "+254799999999", "hello").status == "unknown_number"
    stop = ask(db_session, "+254799999999", "STOP")
    assert stop.status == "unknown_stop" and stop.reply_text is None


def test_registered_checkin_replies_fall_through_to_existing_flow(db_session):
    build_school(db_session)
    for text in ("1", "2", "3", "STOP", "START", "my child is sick"):
        assert ask(db_session, PARENT, text) is None


# ---------- menu & language ----------

def test_menu_in_english_and_swahili(db_session):
    build_school(db_session)
    english = ask(db_session, SINGLE_PARENT, "MENU").reply_text
    swahili = ask(db_session, SINGLE_PARENT, "MSAADA").reply_text
    assert "STATUS" in english and "REPORT <PIN>" in english
    assert "HALI" in swahili and "RIPOTI <PIN>" in swahili


def test_reply_language_follows_alias_and_is_remembered(db_session):
    build_school(db_session)
    log = ask(db_session, SINGLE_PARENT, "HALI")
    assert "Hayupo shuleni leo" in log.reply_text
    assert log.language == "sw"
    # a Kiswahili command word does NOT change the saved preference
    assert db_session.query(GuardianAccount).filter_by(phone=SINGLE_PARENT).one().language == "en"
    assert "Not at school today" in ask(db_session, SINGLE_PARENT, "STATUS").reply_text


# ---------- builders ----------

def test_status_shows_today_and_latest_behaviour(db_session):
    teacher, _, kids = build_school(db_session)
    log_behaviour(db_session, kids[2], teacher, 6, TODAY, "Science")
    reply = ask(db_session, SINGLE_PARENT, "STATUS").reply_text
    assert reply.startswith("Chebet Kiprop (5A) - Wednesday 25 Nov:")
    assert "Not at school today." in reply
    assert "Excellent test score, Science (Tr. Otieno)" in reply


def test_attendance_lists_missed_days_term_and_class_average(db_session):
    build_school(db_session)
    reply = ask(db_session, SINGLE_PARENT, "ATT").reply_text
    assert "Chebet Kiprop - This week: 2/3 days (missed Wednesday)." in reply
    assert "Term:" in reply and "Class average:" in reply


def test_behaviour_reply_shows_last_five_with_icons_and_totals(db_session):
    teacher, _, kids = build_school(db_session)
    for offset, code in enumerate([1, 3, 5, 2, 6, 4, 1]):
        log_behaviour(db_session, kids[2], teacher, code, TODAY - timedelta(days=offset))
    db_session.commit()
    reply = ask(db_session, SINGLE_PARENT, f"BEHAVIOUR {PIN}").reply_text
    assert reply.startswith("Chebet Kiprop - Behaviour this term:")
    assert len(reply.splitlines()) == 1 + 5  # header + last 5 entries
    assert "Participated" in reply
    assert segment_count(reply) <= 2


def test_behaviour_reply_when_no_notes(db_session):
    build_school(db_session)
    assert "No behaviour notes yet" in ask(db_session, SINGLE_PARENT, f"BEHAVIOUR {PIN}").reply_text


def test_report_includes_change_behaviour_risk_and_tip(db_session):
    teacher, _, kids = build_school(db_session)
    log_behaviour(db_session, kids[2], teacher, 4, TODAY)
    db_session.add(RiskSnapshot(learner_id=kids[2].id, date=TODAY, score=40, level="watch", reasons=[]))
    db_session.commit()
    reply = ask(db_session, SINGLE_PARENT, f"REPORT {PIN}").reply_text
    assert reply.startswith("Weekly report - Chebet Kiprop, 5A:")
    assert "Attendance 67%" in reply and "(was 100%)" in reply
    assert "Status:" in reply and "Watch" in reply
    assert "Tip: Ask Chebet about Wednesday." in reply


def test_report_tip_praises_a_good_week(db_session):
    _, _, kids = build_school(db_session)
    parts, _ = pq.build_report(db_session, kids[0], TODAY, "en")
    assert parts[-1].startswith("Tip: Great week! Tell Asha")


def test_every_reply_fits_two_segments_even_with_long_names(db_session):
    teacher, _, kids = build_school(db_session)
    kids[2].name = "Chebet Wanjiru Kiprop-Achieng Mwangangi"
    for offset in range(8):
        log_behaviour(db_session, kids[2], teacher, (offset % 6) + 1, TODAY - timedelta(days=offset), "Social Studies")
    db_session.commit()
    for lang in ("en", "sw"):
        for builder in (pq.build_status, pq.build_attendance, pq.build_behaviour, pq.build_report):
            text = pq.render_sms(builder(db_session, kids[2], TODAY, lang), lang)
            assert segment_count(text) <= 2, (builder.__name__, lang, sms_units(text))
        assert segment_count(pq.render_sms(pq.build_menu(lang), lang)) <= 2


# ---------- multiple children ----------

def test_multi_child_status_returns_combined_summary(db_session):
    build_school(db_session)
    log = ask(db_session, PARENT, "STATUS")
    assert log.status == "ok_combined"
    assert "Asha Njeri: at school today" in log.reply_text
    assert "Baraka Otieno: at school today" in log.reply_text
    assert "Send STATUS 1 for details." in log.reply_text


def test_multi_child_pick_by_number(db_session):
    build_school(db_session)
    assert ask(db_session, PARENT, "STATUS 2").reply_text.startswith("Baraka Otieno (5A)")
    assert ask(db_session, PARENT, f"REPORT 2 {PIN}").reply_text.startswith("Weekly report - Baraka Otieno")


def test_multi_child_report_without_number_asks_which_child(db_session):
    build_school(db_session)
    log = ask(db_session, PARENT, f"REPORT {PIN}")
    assert log.status == "choose_child"
    assert "1 Asha Njeri, 2 Baraka Otieno" in log.reply_text
    assert "REPORT 1 <PIN>" in log.reply_text
    assert ask(db_session, PARENT, "STATUS 7").status == "choose_child"


# ---------- PIN ----------

def test_pin_is_stored_hashed(db_session):
    build_school(db_session)
    account = db_session.query(GuardianAccount).filter_by(phone=PARENT).one()
    assert PIN not in (account.pin_hash or "") and account.pin_salt


def test_status_and_att_need_no_pin_but_behaviour_and_report_do(db_session):
    build_school(db_session)
    assert ask(db_session, SINGLE_PARENT, "STATUS").status == "ok"
    assert ask(db_session, SINGLE_PARENT, "ATT").status == "ok"
    for command in ("BEHAVIOUR", "REPORT", "TABIA", "RIPOTI"):
        log = ask(db_session, SINGLE_PARENT, command)
        assert log.status == "pin_required"
        assert "Chebet" not in log.reply_text


def test_wrong_pins_lock_for_an_hour_then_unlock(db_session):
    build_school(db_session)
    for attempt in range(1, 5):
        log = ask(db_session, SINGLE_PARENT, "REPORT 1111")
        assert log.status == "pin_wrong"
        assert f"{5 - attempt} attempt(s) left" in log.reply_text
    assert ask(db_session, SINGLE_PARENT, "REPORT 1111").status == "pin_locked"
    locked = ask(db_session, SINGLE_PARENT, f"REPORT {PIN}")  # correct PIN is refused while locked
    assert locked.status == "pin_locked" and "Chebet" not in locked.reply_text
    account = db_session.query(GuardianAccount).filter_by(phone=SINGLE_PARENT).one()
    account.locked_until = utc_now_naive() - timedelta(minutes=1)
    db_session.commit()
    assert ask(db_session, SINGLE_PARENT, f"REPORT {PIN}").status == "ok"


def test_correct_pin_resets_failed_attempts(db_session):
    build_school(db_session)
    ask(db_session, SINGLE_PARENT, "REPORT 1111")
    ask(db_session, SINGLE_PARENT, f"REPORT {PIN}")
    assert db_session.query(GuardianAccount).filter_by(phone=SINGLE_PARENT).one().failed_pin_attempts == 0


def test_guardian_without_pin_is_told_to_ask_school(db_session):
    build_school(db_session)
    account = db_session.query(GuardianAccount).filter_by(phone=SINGLE_PARENT).one()
    account.pin_hash = None
    db_session.commit()
    assert ask(db_session, SINGLE_PARENT, f"REPORT {PIN}").status == "no_pin"


def test_pins_are_masked_in_the_log(db_session):
    build_school(db_session)
    log = ask(db_session, SINGLE_PARENT, f"REPORT {PIN}")
    assert PIN not in log.inbound_text
    assert log.inbound_text == "REPORT ****"


# ---------- rate limiting ----------

def test_rate_limit_ten_per_day_then_one_polite_message_then_silence(db_session):
    build_school(db_session)
    for _ in range(10):
        assert ask(db_session, SINGLE_PARENT, "STATUS").status == "ok"
    limited = ask(db_session, SINGLE_PARENT, "STATUS")
    assert limited.status == "rate_limited"
    assert "today's limit of 10" in limited.reply_text
    silent = ask(db_session, SINGLE_PARENT, "STATUS")
    assert silent.status == "rate_limited_silent" and silent.reply_text is None


def test_rate_limit_ignores_yesterday_and_other_numbers(db_session):
    build_school(db_session)
    for _ in range(10):
        db_session.add(MessageLog(phone=SINGLE_PARENT, counted=True, status="ok",
                                  created_at=utc_now_naive() - timedelta(days=2)))
        db_session.add(MessageLog(phone=PARENT, counted=True, status="ok"))
    db_session.commit()
    assert ask(db_session, SINGLE_PARENT, "STATUS").status == "ok"
    assert ask(db_session, PARENT, "STATUS").status == "rate_limited"


# ---------- route + delivery ----------

def test_inbound_route_answers_and_queues_reply(db_session, monkeypatch):
    build_school(db_session)
    queued = []
    monkeypatch.setattr("app.routes.sms.deliver_message_log", lambda log_id: queued.append(log_id))
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as client:
            response = client.post("/sms/inbound", data={"from": "0722000111", "to": "83107", "text": "status"})
    finally:
        app.dependency_overrides.clear()
    assert response.json() == {"status": "ok"}
    log = db_session.query(MessageLog).one()
    assert queued == [log.id]
    assert log.phone == SINGLE_PARENT and log.command == "status"


def test_deliver_message_log_records_send_result(db_session, monkeypatch):
    build_school(db_session)
    log = ask(db_session, SINGLE_PARENT, "STATUS")
    sent = []
    monkeypatch.setattr(
        "app.services.at_client.at_client.send_sms",
        lambda phone, text: sent.append((phone, text)) or {"status": "sent", "message_id": "ATXid_1"},
    )
    pq.deliver_message_log(log.id, db_session)
    assert sent == [(SINGLE_PARENT, log.reply_text)]
    assert log.delivery_status == "sent"


def test_parent_queries_panel_renders(db_session):
    build_school(db_session)
    ask(db_session, SINGLE_PARENT, f"REPORT {PIN}")
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as client:
            panel = client.get("/partials/parent-queries")
            page = client.get("/parent-queries")
    finally:
        app.dependency_overrides.clear()
    assert panel.status_code == 200 and page.status_code == 200
    assert "REPORT ****" in panel.text
    assert "Weekly report - Chebet Kiprop" in panel.text
    assert PIN not in panel.text


# ---------- parent USSD ----------

def test_guardian_dialling_ussd_gets_parent_menu(db_session):
    build_school(db_session)
    menu = handle_ussd(db_session, SINGLE_PARENT, "")
    assert menu.startswith("CON BakiShule - Baba Chebet")
    assert "4. Weekly report" in menu and "5. Contact school" in menu
    assert menu.endswith("6. Change language / Badilisha lugha")
    assert handle_ussd(db_session, SINGLE_PARENT, "1").startswith("END Chebet Kiprop (5A)")
    assert "This week" in handle_ussd(db_session, SINGLE_PARENT, "2")


def test_parent_ussd_requires_pin_for_behaviour_and_report(db_session):
    build_school(db_session)
    assert handle_ussd(db_session, SINGLE_PARENT, "4") == "CON Enter your PIN:"
    assert handle_ussd(db_session, SINGLE_PARENT, "4*1111").startswith("END Wrong PIN")
    assert handle_ussd(db_session, SINGLE_PARENT, f"4*{PIN}").startswith("END Weekly report - Chebet")
    assert handle_ussd(db_session, SINGLE_PARENT, f"3*{PIN}").startswith("END No behaviour notes")
    log = db_session.query(MessageLog).filter_by(channel="ussd", command="report").all()[-1]
    assert PIN not in log.inbound_text


def test_parent_ussd_multi_child_selection(db_session):
    build_school(db_session)
    choose = handle_ussd(db_session, PARENT, "1")
    assert "1. Asha Njeri (5A)" in choose and "2. Baraka Otieno (5A)" in choose
    assert handle_ussd(db_session, PARENT, "1*2").startswith("END Baraka Otieno (5A)")
    assert handle_ussd(db_session, PARENT, f"4*1*{PIN}").startswith("END Weekly report - Asha Njeri")


def test_teacher_who_is_also_a_parent_gets_parent_menu_option(db_session):
    teacher, _, _ = build_school(db_session)
    teacher.phone = SINGLE_PARENT
    db_session.commit()
    menu = handle_ussd(db_session, SINGLE_PARENT, "")
    assert "4. Log behaviour" in menu and "6. Parent menu" in menu
    assert menu.endswith("7. Change language / Badilisha lugha")
    assert handle_ussd(db_session, SINGLE_PARENT, "6").startswith("CON BakiShule - Baba Chebet")
    assert handle_ussd(db_session, SINGLE_PARENT, "6*1").startswith("END Chebet Kiprop (5A)")


# ---------- teacher behaviour logging + risk ----------

def test_teacher_logs_behaviour_over_ussd(db_session):
    build_school(db_session)
    teacher_phone = "+254700123456"
    assert handle_ussd(db_session, teacher_phone, "4").startswith("CON Select class:")
    assert "enter learner roll" in handle_ussd(db_session, teacher_phone, "4*1")
    codes = handle_ussd(db_session, teacher_phone, "4*1*03")
    assert "1. Participated well" in codes and "6. Excellent test score" in codes
    assert "Subject" in handle_ussd(db_session, teacher_phone, "4*1*03*4")
    saved = handle_ussd(db_session, teacher_phone, "4*1*03*4*1")
    assert saved.startswith("END Saved for 03 Chebet Kiprop")
    assert "⚠️ Disruptive (Maths)" in saved
    log = db_session.query(BehaviourLog).one()
    assert (log.code, log.sentiment, log.subject) == (4, "concern", "Maths")
    assert log.teacher.name == "Jane Otieno"


def test_behaviour_flow_skip_subject_and_retry_bad_roll(db_session):
    build_school(db_session)
    phone = "+254700123456"
    assert handle_ussd(db_session, phone, "4*1*99").startswith("CON No roll 99")
    assert "choose" in handle_ussd(db_session, phone, "4*1*99*2")  # retyped roll accepted
    assert handle_ussd(db_session, phone, "4*1*99*2*1*0").startswith("END Saved for 02 Baraka")
    assert db_session.query(BehaviourLog).one().subject is None
    assert handle_ussd(db_session, phone, "4*1*2*9").startswith("END Invalid behaviour code")


def test_repeated_behaviour_concerns_add_risk_signal(db_session):
    teacher, _, kids = build_school(db_session)
    for offset, code in enumerate([2, 3]):
        log_behaviour(db_session, kids[0], teacher, code, TODAY - timedelta(days=offset))
    score_two, reasons_two = calculate_risk(db_session, kids[0], TODAY)
    assert not any("behaviour concerns" in reason for reason in reasons_two)
    log_behaviour(db_session, kids[0], teacher, 4, TODAY - timedelta(days=10))
    score_three, reasons_three = calculate_risk(db_session, kids[0], TODAY)
    assert "3 behaviour concerns in the last 14 days (+8)" in reasons_three
    assert score_three == score_two + 8


def test_old_or_positive_notes_do_not_count_as_concerns(db_session):
    teacher, _, kids = build_school(db_session)
    for code in (1, 5, 6):
        log_behaviour(db_session, kids[0], teacher, code, TODAY)
    for offset in (20, 21, 22):
        log_behaviour(db_session, kids[0], teacher, 3, TODAY - timedelta(days=offset))
    _, reasons = calculate_risk(db_session, kids[0], TODAY)
    assert not any("behaviour concerns" in reason for reason in reasons)
