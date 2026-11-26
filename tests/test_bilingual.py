"""English / Kiswahili behaviour across USSD, SMS replies and outgoing notifications."""
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.messages import t
from app.models import AttendanceRecord, GuardianAccount, Intervention, MessageLog, RiskSnapshot, Teacher
from app.routes.sms import handle_inbound_sms
from app.routes.ussd import handle_ussd
from app.services import parent_queries as pq
from app.services.behaviour import log_behaviour
from app.services.escalation import checkin_message, maybe_escalate
from app.services.sms_format import fit_sms, plain_text, sms_segments, sms_units
from tests.test_parent_queries import PARENT, PIN, SINGLE_PARENT, TODAY, build_school, fixed_today  # noqa: F401

TEACHER = "+254700123456"


def _unset_languages(db_session):
    for account in db_session.query(GuardianAccount):
        account.language = None
    for teacher in db_session.query(Teacher):
        teacher.language = None
    db_session.commit()


def _saved(db_session, phone):
    account = db_session.query(GuardianAccount).filter_by(phone=phone).one_or_none()
    teacher = db_session.query(Teacher).filter_by(phone=phone).one_or_none()
    return (account.language if account else None), (teacher.language if teacher else None)


@pytest.fixture
def sent(monkeypatch):
    """Capture outgoing SMS instead of sending."""
    messages = []
    monkeypatch.setattr(
        "app.services.escalation.at_client.send_sms",
        lambda phone, text: messages.append((phone, text)) or {"status": "mocked"},
    )
    return messages


# ---------- USSD: first-time language screen ----------

LANGUAGE_SCREEN = "CON Karibu BakiShule / Welcome\nChagua lugha / Choose language:\n1. English\n2. Kiswahili"


def test_first_time_teacher_sees_language_screen_then_swahili_menu(db_session):
    build_school(db_session)
    _unset_languages(db_session)
    session = "ATUid_first_teacher"
    assert handle_ussd(db_session, TEACHER, "", session_id=session) == LANGUAGE_SCREEN
    menu = handle_ussd(db_session, TEACHER, "2", session_id=session)
    assert menu == (
        "CON BakiShule - Mwalimu\n1. Andika mahudhurio\n2. Muhtasari wa darasa\n3. Wanafunzi walio hatarini\n"
        "4. Andika tabia\n5. Tafuta mwanafunzi\n6. Badilisha lugha"
    )
    assert _saved(db_session, TEACHER)[1] == "sw"
    # The same session keeps "2" at the front of the chain; it must not be read as a menu choice.
    assert handle_ussd(db_session, TEACHER, "2*1", session_id=session) == (
        "CON Chagua darasa:\n1. 5A (3) - imeandikwa leo\n0. Rudi"
    )


def test_first_time_parent_sees_language_screen_then_swahili_parent_menu(db_session):
    build_school(db_session)
    _unset_languages(db_session)
    session = "ATUid_first_parent"
    assert handle_ussd(db_session, SINGLE_PARENT, "", session_id=session) == LANGUAGE_SCREEN
    assert handle_ussd(db_session, SINGLE_PARENT, "2", session_id=session) == (
        "CON BakiShule - Baba Chebet\n1. Hali ya leo\n2. Mahudhurio\n3. Tabia\n4. Ripoti ya wiki\n"
        "5. Wasiliana na shule\n6. Badilisha lugha"
    )
    assert _saved(db_session, SINGLE_PARENT)[0] == "sw"
    status = handle_ussd(db_session, SINGLE_PARENT, "2*1", session_id=session)
    assert status.startswith("END Chebet Kiprop (5A) - Jumatano 25 Nov:")
    assert handle_ussd(db_session, SINGLE_PARENT, "2*4", session_id=session) == "CON Ingiza PIN yako:"


def test_first_time_invalid_language_choice(db_session):
    build_school(db_session)
    _unset_languages(db_session)
    assert handle_ussd(db_session, TEACHER, "9", session_id="s") == (
        "END Chaguo si sahihi, jaribu tena. / Invalid choice, try again."
    )


def test_returning_user_skips_language_screen(db_session):
    build_school(db_session)
    assert handle_ussd(db_session, TEACHER, "", session_id="later").startswith("CON BakiShule - Teacher")


def test_unknown_number_gets_bilingual_not_registered(db_session):
    build_school(db_session)
    assert handle_ussd(db_session, "+254799000000", "") == (
        "END Namba hii haijasajiliwa. Tafadhali wasiliana na shule yako. / "
        "This number is not registered. Please contact your school."
    )


# ---------- USSD: change language from both menus ----------

def test_teacher_changes_language_from_menu(db_session):
    build_school(db_session)
    assert handle_ussd(db_session, TEACHER, "6") == LANGUAGE_SCREEN
    confirmed = handle_ussd(db_session, TEACHER, "6*2")
    assert confirmed.startswith("CON Lugha: Kiswahili\n1. Andika mahudhurio")
    assert confirmed.endswith("6. Badilisha lugha")
    assert _saved(db_session, TEACHER)[1] == "sw"
    assert handle_ussd(db_session, TEACHER, "").startswith("CON BakiShule - Mwalimu")
    # change back and keep navigating in the same chain
    assert handle_ussd(db_session, TEACHER, "6*1*2").startswith("CON Select class:")
    assert _saved(db_session, TEACHER)[1] == "en"


def test_parent_changes_language_from_menu(db_session):
    build_school(db_session)
    assert handle_ussd(db_session, SINGLE_PARENT, "6") == LANGUAGE_SCREEN
    confirmed = handle_ussd(db_session, SINGLE_PARENT, "6*2")
    assert confirmed.startswith("CON Lugha: Kiswahili\n1. Hali ya leo")
    assert confirmed.endswith("6. Badilisha lugha")
    assert _saved(db_session, SINGLE_PARENT)[0] == "sw"
    assert handle_ussd(db_session, SINGLE_PARENT, "6*2*2").startswith("END Chebet Kiprop - Wiki hii:")
    teacher = db_session.query(Teacher).one()
    teacher.phone = PARENT  # a teacher who is also a parent has 7 options; all must survive the confirmation
    db_session.commit()
    both = handle_ussd(db_session, PARENT, "7*2")
    assert both.startswith("CON Lugha: Kiswahili") and both.endswith("7. Badilisha lugha")


def test_swahili_navigation_and_behaviour_codes(db_session):
    build_school(db_session)
    handle_ussd(db_session, TEACHER, "6*2")
    assert handle_ussd(db_session, TEACHER, "4").endswith("0. Rudi")
    assert handle_ussd(db_session, TEACHER, "4*0").startswith("CON BakiShule - Mwalimu")  # Rudi = back
    assert handle_ussd(db_session, TEACHER, "1*1").endswith("00. Menyu kuu")
    codes = handle_ussd(db_session, TEACHER, "4*1*03")
    assert codes.startswith("CON 03 Chebet: chagua")
    for line in ["1. Alishiriki vizuri ⭐", "2. Hakufanya kazi ya nyumbani ⚠️", "3. Alichelewa darasani ⚠️",
                 "4. Alisumbua darasani ⚠️", "5. Aliwasaidia wenzake ⭐", "6. Alama bora mtihanini ⭐"]:
        assert line in codes
    saved = handle_ussd(db_session, TEACHER, "4*1*03*1*1")
    assert saved.startswith("END Imehifadhiwa kwa 03 Chebet Kiprop:")
    assert "⭐ Alishiriki vizuri (Hisabati)" in saved
    assert handle_ussd(db_session, TEACHER, "9") == "END Chaguo si sahihi, jaribu tena."


def test_every_swahili_ussd_screen_fits(db_session):
    build_school(db_session)
    handle_ussd(db_session, TEACHER, "6*2")
    handle_ussd(db_session, SINGLE_PARENT, "6*2")
    for phone, chains in {
        TEACHER: ["", "1", "1*1", "1*1*01 02 03", "2*1", "3*1", "4*1*01", "4*1*01*2", "5*1*1", "6"],
        SINGLE_PARENT: ["", "1", "2", "3", f"3*{PIN}", f"4*{PIN}", "5", "6"],
    }.items():
        for chain in chains:
            assert len(handle_ussd(db_session, phone, chain)) <= 182, (phone, chain)


def test_parent_contact_school_forwards_to_teacher_in_teacher_language(db_session, sent):
    build_school(db_session)
    handle_ussd(db_session, TEACHER, "6*2")  # teacher prefers Kiswahili
    assert handle_ussd(db_session, SINGLE_PARENT, "5") == "CON Type your message to the school:"
    done = handle_ussd(db_session, SINGLE_PARENT, "5*Chebet has a clinic visit Friday")
    assert done == "END Sent. The class teacher will get back to you."
    assert sent == [(TEACHER, "Ujumbe kutoka kwa mzazi wa Chebet Kiprop: Chebet has a clinic visit Friday")]


# ---------- SMS: language commands ----------

@pytest.mark.parametrize("text, lang", [
    ("ENGLISH", "en"), ("kiswahili", "sw"), ("LANG EN", "en"), ("lang sw", "sw"),
    ("LUGHA EN", "en"), ("Lugha SW", "sw"),
])
def test_sms_language_commands_save_and_reply_with_menu(db_session, text, lang):
    build_school(db_session)
    log = pq.handle_sms_query(db_session, SINGLE_PARENT, text)
    assert log.status == "language_set"
    assert _saved(db_session, SINGLE_PARENT)[0] == lang
    assert log.reply_text == t("menu", lang)


def test_swahili_menu_lists_the_commands(db_session):
    menu = t("menu", "sw")
    for word in ("HALI", "MAHUDHURIO", "TABIA", "RIPOTI", "LUGHA", "ACHA"):
        assert word in menu


def test_lang_without_choice_gets_bilingual_prompt(db_session):
    build_school(db_session)
    log = pq.handle_sms_query(db_session, SINGLE_PARENT, "LUGHA")
    assert log.status == "language_prompt" and "LUGHA SW" in log.reply_text and "LANG EN" in log.reply_text


def test_language_command_also_sets_teacher_language_for_same_phone(db_session):
    teacher, _, _ = build_school(db_session)
    teacher.phone = SINGLE_PARENT
    db_session.commit()
    pq.handle_sms_query(db_session, SINGLE_PARENT, "KISWAHILI")
    assert _saved(db_session, SINGLE_PARENT) == ("sw", "sw")


# ---------- SMS: reply language rules ----------

def test_swahili_command_gets_swahili_reply_without_changing_preference(db_session):
    build_school(db_session)  # saved preference: English
    reply = pq.handle_sms_query(db_session, SINGLE_PARENT, "HALI").reply_text
    assert "Yuko shuleni" in reply or "Hayupo shuleni" in reply
    assert _saved(db_session, SINGLE_PARENT)[0] == "en"
    assert pq.handle_sms_query(db_session, SINGLE_PARENT, "MSAADA").reply_text == t("menu", "sw")


def test_english_command_gets_english_reply_even_if_preference_is_swahili(db_session):
    build_school(db_session)
    pq.handle_sms_query(db_session, SINGLE_PARENT, "LUGHA SW")
    assert pq.handle_sms_query(db_session, SINGLE_PARENT, "ATT").reply_text.startswith("Chebet Kiprop - This week")
    assert _saved(db_session, SINGLE_PARENT)[0] == "sw"


def test_neutral_input_uses_saved_preference(db_session, sent):
    _, _, kids = build_school(db_session)
    pq.handle_sms_query(db_session, SINGLE_PARENT, "LUGHA SW")
    handle_inbound_sms(db_session, SINGLE_PARENT, "1")
    assert (SINGLE_PARENT, t("ack_1", "sw", names="Chebet Kiprop")) in sent
    handle_inbound_sms(db_session, PARENT, "1")  # English preference
    assert (PARENT, t("ack_1", "en", names="Asha Njeri & Baraka Otieno")) in sent


def test_neutral_input_defaults_to_english_when_not_set(db_session, sent):
    build_school(db_session)
    _unset_languages(db_session)
    handle_inbound_sms(db_session, SINGLE_PARENT, "3")
    assert sent[-1] == (SINGLE_PARENT, t("ack_3", "en", names="Chebet Kiprop"))


def test_pin_on_its_own_is_not_forwarded_and_uses_saved_language(db_session, sent):
    build_school(db_session)
    pq.handle_sms_query(db_session, SINGLE_PARENT, "LUGHA SW")
    log = pq.handle_sms_query(db_session, SINGLE_PARENT, PIN)
    assert log.status == "pin_only" and log.reply_text.startswith("Tuma PIN pamoja na amri")
    assert sent == []  # nothing went to the teacher


def test_acha_and_anza_opt_out_and_in_with_swahili_ack(db_session, sent):
    _, _, kids = build_school(db_session)
    handle_inbound_sms(db_session, SINGLE_PARENT, "ACHA")
    assert kids[2].sms_opt_out is True and sent == []
    handle_inbound_sms(db_session, SINGLE_PARENT, "anza")
    assert kids[2].sms_opt_out is False
    assert sent == [(SINGLE_PARENT, t("ack_start", "sw", names="Chebet Kiprop"))]


# ---------- SMS: first contact welcome ----------

def test_first_contact_without_language_gets_welcome_once_and_still_an_answer(db_session):
    build_school(db_session)
    _unset_languages(db_session)
    welcome = pq.language_prompt_if_needed(db_session, SINGLE_PARENT, "HALI")
    assert welcome.reply_text == (
        "Karibu BakiShule! Tuma KISWAHILI au ENGLISH kuchagua lugha. / "
        "Reply ENGLISH or KISWAHILI to choose your language."
    )
    answer = pq.handle_sms_query(db_session, SINGLE_PARENT, "HALI")
    assert "shuleni leo" in answer.reply_text  # answered in the language it was written in
    assert pq.language_prompt_if_needed(db_session, SINGLE_PARENT, "STATUS") is None  # only once
    assert pq.language_prompt_if_needed(db_session, SINGLE_PARENT, "KISWAHILI") is None


def test_no_welcome_when_language_already_set_or_number_unknown(db_session):
    build_school(db_session)
    assert pq.language_prompt_if_needed(db_session, SINGLE_PARENT, "STATUS") is None
    assert pq.language_prompt_if_needed(db_session, "+254799000000", "STATUS") is None


def test_reset_language_shows_welcome_again(db_session):
    build_school(db_session)
    _unset_languages(db_session)
    pq.language_prompt_if_needed(db_session, SINGLE_PARENT, "STATUS")
    pq.handle_sms_query(db_session, SINGLE_PARENT, "ENGLISH")
    pq.reset_language(db_session, SINGLE_PARENT)
    assert _saved(db_session, SINGLE_PARENT)[0] is None
    assert pq.language_prompt_if_needed(db_session, SINGLE_PARENT, "STATUS") is not None


# ---------- Kiswahili reply formats (spec examples) ----------

def test_swahili_reply_formats(db_session, monkeypatch):
    teacher, _, kids = build_school(db_session)
    monkeypatch.setattr("app.services.sms_format.settings", SimpleNamespace(sms_use_emoji=True))
    amani = kids[2]
    amani.name = "Amani"
    log_behaviour(db_session, amani, teacher, 1, TODAY)
    db_session.add(RiskSnapshot(learner_id=amani.id, date=TODAY, score=35, level="watch", reasons=[]))
    db_session.commit()
    parts, sep = pq.build_status(db_session, amani, TODAY, "sw")
    assert sep.join(parts) == (
        "Amani (5A) - Jumatano 25 Nov: ⚠️ Hayupo shuleni leo. Mwisho: ⭐ Alishiriki vizuri (Mwl. Otieno). "
        "Tuma MAHUDHURIO, TABIA au RIPOTI kwa zaidi."
    )
    # With emojis that is 140 UCS-2 units (> 134 for 2 segments), so the plain fallback is sent:
    assert pq.render_sms((parts, sep), "sw") == (
        "Amani (5A) - Jumatano 25 Nov: ! Hayupo shuleni leo. Mwisho: * Alishiriki vizuri (Mwl. Otieno). "
        "Tuma MAHUDHURIO, TABIA au RIPOTI kwa zaidi."
    )
    att = pq.render_sms(pq.build_attendance(db_session, amani, TODAY, "sw"), "sw")
    assert att.startswith("Amani - Wiki hii: siku 2/3 (hakuja Jumatano). Muhula: ")
    assert "Wastani wa darasa:" in att
    parts, sep = pq.build_report(db_session, amani, TODAY, "sw")
    assert sep.join(parts) == (
        "Ripoti ya wiki - Amani, 5A: Mahudhurio 67% ⬇️ (ilikuwa 100%). Tabia 1⭐ 0⚠️. Hali: 🟡 Angalia. "
        "Ushauri: Muulize Amani kuhusu Jumatano. Tuma 2 kama karo ni changamoto."
    )
    ripoti = pq.render_sms((parts, sep), "sw")  # too long with emojis -> plain fallback, nothing dropped
    assert ripoti == (
        "Ripoti ya wiki - Amani, 5A: Mahudhurio 67% chini (ilikuwa 100%). Tabia 1* 0!. Hali: Angalia. "
        "Ushauri: Muulize Amani kuhusu Jumatano. Tuma 2 kama karo ni changamoto."
    )
    assert sms_segments(ripoti) <= 2


# ---------- segments & emoji fallback ----------

def test_sms_segments_gsm_and_ucs2():
    assert sms_units("Habari") == ("gsm7", 6)
    assert sms_segments("a" * 160) == 1 and sms_segments("a" * 161) == 2 and sms_segments("a" * 307) == 3
    assert sms_units("✅ sawa")[0] == "ucs2"
    assert sms_segments("⭐" + "a" * 69) == 1 and sms_segments("⭐" + "a" * 70) == 2
    assert sms_segments("⭐" + "a" * 133) == 2 and sms_segments("⭐" + "a" * 134) == 3
    assert sms_units("x{y}")[1] == 6  # GSM extended chars count double


def test_plain_text_fallback_in_both_languages():
    assert plain_text("Tabia 3⭐ 2⚠️. Hali: 🟡 Angalia. ✅ 80% ⬇️", "sw") == "Tabia 3* 2!. Hali: Angalia. OK 80% chini"
    assert plain_text("Up ⬆️ 🔴 High", "en") == "Up up High"
    assert sms_units(plain_text("⭐⚠️✅⬇️⬆️🟢🟡🟠🔴", "en"))[0] == "gsm7"


def test_fit_keeps_emoji_when_short_and_falls_back_when_long(monkeypatch):
    monkeypatch.setattr("app.services.sms_format.settings", SimpleNamespace(sms_use_emoji=True))
    assert fit_sms(["Tabia 3⭐ 2⚠️"], "sw") == "Tabia 3⭐ 2⚠️"
    long_parts = ["Ripoti ya wiki ⭐" + "x" * 100, "Hali: 🟡 Angalia " + "y" * 60]
    text = fit_sms(long_parts, "sw", sep=" ")
    assert "⭐" not in text and "🟡" not in text and sms_segments(text) <= 2
    assert "*" in text and "Angalia" in text  # nothing dropped, just plain


def test_sms_use_emoji_false_always_uses_plain(monkeypatch):
    monkeypatch.setattr("app.services.sms_format.settings", SimpleNamespace(sms_use_emoji=False))
    assert fit_sms(["Tabia 3⭐ 2⚠️"], "sw") == "Tabia 3* 2!"


def test_all_builders_fit_two_segments_with_longest_names_both_languages(db_session):
    teacher, classroom, kids = build_school(db_session)
    teacher.name = "Wanjiku Nyambura-Kamau Wairimu"
    classroom.name = "Grade 7 East"
    for kid in kids:
        kid.name = "Nyambura Wanjiru-Achieng Mwangangi Kiprotich"
    for offset in range(10):
        log_behaviour(db_session, kids[0], teacher, (offset % 6) + 1, TODAY - timedelta(days=offset), "Social Studies")
    db_session.add(RiskSnapshot(learner_id=kids[0].id, date=TODAY, score=90, level="critical", reasons=[]))
    db_session.commit()
    for lang in ("en", "sw"):
        builds = [builder(db_session, kids[0], TODAY, lang) for builder in pq.BUILDERS.values()]
        builds += [pq.build_menu(lang), pq.build_combined(db_session, kids[:2], TODAY, lang, "status", "HALI"),
                   pq.build_combined(db_session, kids[:2], TODAY, lang, "att", "ATT")]
        for built in builds:
            text = pq.render_sms(built, lang)
            assert sms_segments(text) <= 2, (lang, sms_units(text), text)
        assert sms_segments(checkin_message(db_session, kids[0], TODAY)) <= 2


# ---------- outgoing notifications follow the recipient's language ----------

def _make_absent(db_session, learner, days):
    for offset in range(days):
        day = TODAY - timedelta(days=offset)
        record = db_session.query(AttendanceRecord).filter_by(learner_id=learner.id, date=day).one_or_none()
        if record:
            record.present = False
    db_session.commit()


def test_checkin_sms_lists_missed_days_in_guardian_language(db_session):
    _, _, kids = build_school(db_session)
    _make_absent(db_session, kids[2], 2)  # Tuesday + Wednesday
    pq.handle_sms_query(db_session, SINGLE_PARENT, "LUGHA SW")
    assert checkin_message(db_session, kids[2], TODAY) == (
        "Hatukumwona Chebet Kiprop Jumanne na Jumatano. Kila kitu kiko sawa? Jibu 1 Mgonjwa, 2 Karo, 3 Mengineyo."
    )
    pq.handle_sms_query(db_session, SINGLE_PARENT, "LANG EN")
    assert checkin_message(db_session, kids[2], TODAY) == (
        "We missed Chebet Kiprop on Tuesday and Wednesday. Is everything okay? Reply 1 Sick, 2 Fees, 3 Other."
    )


def test_escalation_alerts_use_each_recipients_language(db_session, sent):
    teacher, classroom, kids = build_school(db_session)
    head = Teacher(name="Grace Wanjiku", phone="+254700999888", role="head_teacher", language="en")
    from app.models import ClassRoom
    db_session.add_all([head, ClassRoom(name="6A", school=classroom.school, teacher=head)])
    teacher.language = "sw"
    pq.handle_sms_query(db_session, SINGLE_PARENT, "LUGHA SW")
    _make_absent(db_session, kids[2], 3)
    snapshot = RiskSnapshot(learner_id=kids[2].id, date=TODAY, score=60, level="at_risk",
                            reasons=["3 consecutive school-day absences (+30)"])
    db_session.add(snapshot)
    db_session.commit()
    maybe_escalate(db_session, kids[2], snapshot, "green")
    by_phone = {phone: text for phone, text in sent}
    assert by_phone[SINGLE_PARENT].startswith("Hatukumwona Chebet Kiprop Jumatatu, Jumanne na Jumatano.")
    assert by_phone[TEACHER] == "Hatarini: Chebet Kiprop (5A). Hakuja siku 3 mfululizo"
    assert by_phone[head.phone] == "At-risk: Chebet Kiprop (5A). 3 absences in a row"


def test_teacher_alert_from_parent_reply_uses_teacher_language(db_session, sent):
    teacher, _, _ = build_school(db_session)
    teacher.language = "sw"
    db_session.commit()
    handle_inbound_sms(db_session, SINGLE_PARENT, "1")
    assert (TEACHER, "Mzazi anasema Chebet Kiprop ni mgonjwa. Tafadhali fuatilia.") in sent
    assert (SINGLE_PARENT, t("ack_1", "en", names="Chebet Kiprop")) in sent


def test_sponsor_receipts_use_each_recipients_language(db_session, sent, monkeypatch):
    from fastapi.testclient import TestClient

    from app.db import get_db
    from app.main import app

    teacher, _, kids = build_school(db_session)
    pq.handle_sms_query(db_session, SINGLE_PARENT, "LUGHA SW")
    db_session.add(Intervention(learner_id=kids[2].id, type="sponsor_flag", status="open", metadata_json={}))
    db_session.commit()
    monkeypatch.setattr("app.routes.dashboard.payment_service.pay_sponsor_fee",
                        lambda **kwargs: {"status": "mocked"})
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as client:
            client.post(f"/sponsors/{kids[2].id}/pay", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()
    by_phone = dict(sent)
    assert by_phone[SINGLE_PARENT] == "Msaada wa karo wa KES 3,000 umepangwa kwa Chebet Kiprop."
    assert by_phone[TEACHER] == "Fee support of KES 3,000 has been arranged for Chebet Kiprop."


def test_reward_message_uses_guardian_language(db_session, sent):
    _, _, kids = build_school(db_session)
    pq.handle_sms_query(db_session, SINGLE_PARENT, "KISWAHILI")
    from app.services.escalation import _log_send, guardian_reply_language

    lang = guardian_reply_language(db_session, SINGLE_PARENT)
    _log_send(db_session, kids[2], "airtime_reward", SINGLE_PARENT,
              t("reward_congrats", lang, first="Chebet", amount=20))
    assert sent[-1][1].startswith("Hongera Chebet! Umekamilisha wiki 4")


def test_message_log_records_language_for_badges(db_session):
    build_school(db_session)
    pq.handle_sms_query(db_session, SINGLE_PARENT, "HALI")
    pq.handle_sms_query(db_session, SINGLE_PARENT, "STATUS")
    pq.handle_sms_query(db_session, "+254799000000", "HALI")
    languages = [log.language for log in db_session.query(MessageLog).order_by(MessageLog.id)]
    assert languages == ["sw", "en", None]  # None = bilingual (unknown number)


# ---------- dashboard ----------

def test_dashboard_language_controls_and_badges(db_session, monkeypatch):
    from fastapi.testclient import TestClient

    from app.db import get_db
    from app.main import app

    teacher, _, kids = build_school(db_session)
    pq.handle_sms_query(db_session, SINGLE_PARENT, "HALI")
    pq.handle_sms_query(db_session, SINGLE_PARENT, "STATUS")
    monkeypatch.setattr("app.routes.dashboard.settings", SimpleNamespace(demo_mode=True,
                                                                          demo_parent_phone=SINGLE_PARENT))
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as client:
            page = client.get("/teachers")
            assert page.status_code == 200 and "Jane Otieno" in page.text and 'value="sw"' in page.text
            client.post(f"/teachers/{teacher.id}/language", data={"language": "sw"}, follow_redirects=False)
            assert _saved(db_session, TEACHER)[1] == "sw"
            learner_page = client.get(f"/learners/{kids[2].id}")
            assert "Not chosen yet" in learner_page.text and 'action="/guardians/language"' in learner_page.text
            client.post("/guardians/language", data={"phone": SINGLE_PARENT, "language": "sw",
                                                     "back": f"/learners/{kids[2].id}"}, follow_redirects=False)
            assert _saved(db_session, SINGLE_PARENT)[0] == "sw"
            panel = client.get("/partials/parent-queries").text
            assert ">SW<" in panel and ">EN<" in panel
            assert "Reset language for demo guardian" in client.get("/").text
            client.post("/demo/reset-language", follow_redirects=False)
            assert _saved(db_session, SINGLE_PARENT)[0] is None
    finally:
        app.dependency_overrides.clear()
