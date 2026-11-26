"""AI SMS chat: free-text parent messages answered from the child's data (Claude call faked)."""
import json

import pytest

from app.messages import t
from app.models import MessageLog, ParentReply
from app.routes.sms import handle_inbound_sms
from app.services import ai_chat
from tests.test_parent_queries import PARENT, PIN, SINGLE_PARENT, build_school, fixed_today  # noqa: F401

TEACHER = "+254700123456"


@pytest.fixture
def claude(monkeypatch):
    """Fake Claude: records what it was sent and returns a scripted answer."""
    calls = []
    answer = {"reply": "Chebet came 2 of 3 days this week.", "language": "en", "intent": "question",
              "child_number": 0}

    def fake(system, messages):
        calls.append({"system": system, "messages": messages})
        return dict(answer) if answer is not None else None

    monkeypatch.setattr(ai_chat, "call_claude", fake)
    monkeypatch.setattr(ai_chat, "ai_enabled", lambda: True)
    monkeypatch.setattr("app.routes.sms.ai_enabled", lambda: True)
    return SimpleFake(calls, answer)


class SimpleFake:
    def __init__(self, calls, answer):
        self.calls, self.answer = calls, answer

    def facts(self, index=-1):
        content = self.calls[index]["messages"][-1]["content"]
        return json.loads(content.split("<facts>\n", 1)[1].split("\n</facts>", 1)[0])

    def parent_text(self, index=-1):
        content = self.calls[index]["messages"][-1]["content"]
        return content.split("<parent_message>\n", 1)[1].split("\n</parent_message>", 1)[0]


@pytest.fixture
def sent(monkeypatch):
    messages = []
    send = lambda phone, text: messages.append((phone, text)) or {"status": "mocked"}  # noqa: E731
    monkeypatch.setattr("app.services.escalation.at_client.send_sms", send)
    return messages


def test_swahili_question_gets_ai_reply_from_real_data(db_session, claude, sent):
    build_school(db_session)
    claude.answer.update(reply="Chebet amekuja siku 2 kati ya 3 wiki hii. Hakuja Jumatano.", language="sw")
    handle_inbound_sms(db_session, SINGLE_PARENT, "Mtoto wangu anaendelea vipi?")

    facts = claude.facts()
    child = facts["children"][0]
    assert child["name"] == "Chebet Kiprop" and child["class"] == "5A"
    assert child["this_week"] == {"days_present": 2, "school_days_marked": 3, "days_missed": ["Wednesday"]}
    assert child["today"] == "absent" and facts["private_details_unlocked"] is False
    assert "behaviour_this_term" not in child and "support_status" not in child
    assert claude.parent_text() == "Mtoto wangu anaendelea vipi?"

    assert sent == [(SINGLE_PARENT, "Chebet amekuja siku 2 kati ya 3 wiki hii. Hakuja Jumatano.")]
    log = db_session.query(MessageLog).one()
    assert (log.command, log.language, log.status) == ("chat_question", "sw", "ok")
    assert log.inbound_text == "Mtoto wangu anaendelea vipi?"


def test_no_phone_numbers_or_guardian_names_are_sent_to_claude(db_session, claude, sent):
    build_school(db_session)
    handle_inbound_sms(db_session, PARENT, "How are my children doing?")
    payload = json.dumps(claude.calls[-1]["messages"])
    for secret in (PARENT, SINGLE_PARENT, TEACHER, "Mama Asha", "Baba Chebet"):
        assert secret not in payload
    assert [c["name"] for c in claude.facts()["children"]] == ["Asha Njeri", "Baraka Otieno"]


def test_pin_in_message_unlocks_private_details_but_is_never_sent(db_session, claude, sent):
    build_school(db_session)
    handle_inbound_sms(db_session, SINGLE_PARENT, f"How is my child performing? PIN {PIN}")
    facts = claude.facts()
    assert facts["pin_status"] == "ok" and facts["private_details_unlocked"] is True
    assert "behaviour_this_term" in facts["children"][0] and "support_status" in facts["children"][0]
    assert PIN not in json.dumps(claude.calls[-1]["messages"])
    assert claude.parent_text() == "How is my child performing? PIN ****"
    assert PIN not in db_session.query(MessageLog).one().inbound_text
    assert all(PIN not in reply.raw_text for reply in db_session.query(ParentReply))


def test_wrong_pin_is_reported_and_counts_toward_lock(db_session, claude, sent):
    build_school(db_session)
    handle_inbound_sms(db_session, SINGLE_PARENT, "Ripoti ya mtoto 1111")
    assert claude.facts()["pin_status"] == "wrong"
    assert claude.facts()["private_details_unlocked"] is False


def test_sick_intent_alerts_teacher_for_that_child_only(db_session, claude, sent):
    build_school(db_session)
    claude.answer.update(reply="Pole sana. Mwalimu amejulishwa.", language="sw", intent="report_sick",
                         child_number=2)
    handle_inbound_sms(db_session, PARENT, "Baraka ni mgonjwa leo, hataenda shule")
    assert (TEACHER, "Parent reports Baraka Otieno is sick. Please follow up.") in sent
    assert not any("Asha" in text for phone, text in sent if phone == TEACHER)
    assert sent[-1] == (PARENT, "Pole sana. Mwalimu amejulishwa.")
    assert [r.code for r in db_session.query(ParentReply)] == [1]


def test_fees_intent_flags_for_sponsor_support(db_session, claude, sent):
    _, _, kids = build_school(db_session)
    claude.answer.update(intent="report_fees", child_number=1, reply="Thank you. The school will contact you.")
    handle_inbound_sms(db_session, SINGLE_PARENT, "We have no money for school fees this month")
    from app.models import Intervention
    flag = db_session.query(Intervention).filter_by(type="sponsor_flag", learner_id=kids[2].id).one()
    assert flag.metadata_json["reason"] == "parent_fees"


def test_message_for_teacher_is_forwarded(db_session, claude, sent):
    build_school(db_session)
    claude.answer.update(intent="message_for_teacher", child_number=1,
                         reply="I have passed your message to Tr. Otieno.")
    handle_inbound_sms(db_session, SINGLE_PARENT, "Please ask the teacher to call me about the trip")
    assert (TEACHER, "Parent reply about Chebet Kiprop: Please ask the teacher to call me about the trip") in sent


def test_question_is_not_forwarded_to_teacher(db_session, claude, sent):
    build_school(db_session)
    handle_inbound_sms(db_session, SINGLE_PARENT, "How is my child doing?")
    assert all(phone != TEACHER for phone, _ in sent)


def test_follow_up_includes_recent_conversation(db_session, claude, sent):
    build_school(db_session)
    handle_inbound_sms(db_session, SINGLE_PARENT, "How is my child doing?")
    handle_inbound_sms(db_session, SINGLE_PARENT, "And last week?")
    history = claude.calls[-1]["messages"]
    assert history[0] == {"role": "user", "content": "How is my child doing?"}
    assert history[1] == {"role": "assistant", "content": "Chebet came 2 of 3 days this week."}
    assert history[2]["role"] == "user" and "And last week?" in history[2]["content"]


def test_ai_failure_falls_back_to_forward_and_thanks(db_session, monkeypatch, sent):
    build_school(db_session)
    monkeypatch.setattr(ai_chat, "call_claude", lambda system, messages: None)
    monkeypatch.setattr(ai_chat, "ai_enabled", lambda: True)
    monkeypatch.setattr("app.routes.sms.ai_enabled", lambda: True)
    handle_inbound_sms(db_session, SINGLE_PARENT, "How is my child doing?")
    assert (TEACHER, "Parent reply about Chebet Kiprop: How is my child doing?") in sent
    assert sent[-1] == (SINGLE_PARENT, t("ack_3", "en", names="Chebet Kiprop"))


def test_ai_disabled_keeps_old_behaviour(db_session, sent):
    build_school(db_session)
    handle_inbound_sms(db_session, SINGLE_PARENT, "How is my child doing?")
    assert sent[-1] == (SINGLE_PARENT, t("ack_3", "en", names="Chebet Kiprop"))


def test_numbered_replies_and_commands_never_go_to_ai(db_session, claude, sent):
    from app.services.parent_queries import handle_sms_query

    build_school(db_session)
    handle_inbound_sms(db_session, SINGLE_PARENT, "1")
    handle_sms_query(db_session, SINGLE_PARENT, "HALI")
    assert claude.calls == []


def test_long_ai_reply_is_trimmed_to_two_segments(db_session, claude, sent):
    from app.services.sms_format import sms_segments

    build_school(db_session)
    claude.answer.update(reply="Chebet is doing well. " * 30)
    handle_inbound_sms(db_session, SINGLE_PARENT, "How is she?")
    assert sms_segments(sent[-1][1]) <= 2


def test_chat_counts_toward_daily_limit(db_session, claude, sent, monkeypatch):
    build_school(db_session)
    import dataclasses

    from app.services import parent_queries

    monkeypatch.setattr(parent_queries, "settings",
                        dataclasses.replace(parent_queries.settings, parent_daily_query_limit=2))
    monkeypatch.setattr("app.routes.sms.settings", parent_queries.settings)
    for _ in range(4):
        handle_inbound_sms(db_session, SINGLE_PARENT, "How is my child doing?")
    assert len(claude.calls) == 2
    statuses = [log.status for log in db_session.query(MessageLog).order_by(MessageLog.id)]
    assert statuses == ["ok", "ok", "rate_limited", "rate_limited_silent"]
