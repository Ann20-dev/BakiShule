import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

import app.services.at_client as at_client_module
from app.services.at_client import AfricaTalkingClient


def test_dry_run_uses_mocked_responses_without_sdk_calls(monkeypatch):
    sdk = ModuleType("africastalking")
    sdk.initialize = Mock()
    monkeypatch.setitem(sys.modules, "africastalking", sdk)
    monkeypatch.setattr(
        at_client_module,
        "settings",
        SimpleNamespace(
            dry_run=True,
            at_api_key="",
            at_username="sandbox",
            at_sender_id="",
        ),
    )
    client = AfricaTalkingClient()

    assert client.send_sms("+254700000001", "Test") == {
        "status": "mocked",
        "dry_run": True,
    }
    assert client.send_airtime("+254700000001", 20) == {
        "status": "mocked",
        "dry_run": True,
    }
    assert client.send_mobile_data("demo", "+254700000001", 1, "GB", "Month") == {
        "status": "mocked",
        "dry_run": True,
    }
    sdk.initialize.assert_not_called()


def test_live_adapter_maps_arguments_to_sdk_services(monkeypatch):
    sdk = ModuleType("africastalking")
    sdk.initialize = Mock()
    sms_response = {
        "SMSMessageData": {
            "Message": "Sent to 1/1 Total Cost: KES 0.8000",
            "Recipients": [
                {"statusCode": 101, "number": "+254700000001", "status": "Success",
                 "cost": "KES 0.8000", "messageId": "ATXid_1"}
            ],
        }
    }
    airtime_response = {"errorMessage": "None", "numSent": 1}
    data_response = {"status": "success"}
    sdk.SMS = SimpleNamespace(send=Mock(return_value=sms_response))
    sdk.Airtime = SimpleNamespace(send=Mock(return_value=airtime_response))
    sdk.MobileData = SimpleNamespace(send=Mock(return_value=data_response))
    monkeypatch.setitem(sys.modules, "africastalking", sdk)
    monkeypatch.setattr(
        at_client_module,
        "settings",
        SimpleNamespace(
            dry_run=False,
            at_api_key="synthetic-key",
            at_username="sandbox",
            at_sender_id="BAKISHULE",
        ),
    )
    client = AfricaTalkingClient()

    sms_result = client.send_sms("+254700000001", "Check-in")
    assert sms_result["status"] == "sent"
    assert sms_result["message_id"] == "ATXid_1"
    assert sms_result["raw"] is sms_response
    assert client.send_airtime("+254700000001", 20) is airtime_response
    assert client.send_mobile_data(
        "demo-bundle", "+254700000001", 1.5, "GB", "Month"
    ) is data_response

    sdk.initialize.assert_called_once_with("sandbox", "synthetic-key")
    sdk.SMS.send.assert_called_once_with(
        "Check-in", ["+254700000001"], sender_id="BAKISHULE"
    )
    sdk.Airtime.send.assert_called_once_with(
        phone_number="+254700000001",
        amount="20",
        currency_code="KES",
    )
    sdk.MobileData.send.assert_called_once_with(
        "demo-bundle",
        [
            {
                "phoneNumber": "+254700000001",
                "quantity": 1.5,
                "unit": "GB",
                "validity": "Month",
            }
        ],
    )


def test_live_adapter_requires_api_key(monkeypatch):
    monkeypatch.setattr(
        at_client_module,
        "settings",
        SimpleNamespace(
            dry_run=False,
            at_api_key="",
            at_username="sandbox",
            at_sender_id="",
        ),
    )

    with pytest.raises(RuntimeError, match="AT_API_KEY is required"):
        AfricaTalkingClient()


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("0707274525", "+254707274525"),
        ("0707 274-525", "+254707274525"),
        ("254707274525", "+254707274525"),
        ("00254707274525", "+254707274525"),
        ("+254707274525", "+254707274525"),
        ("707274525", "+707274525"),
    ],
)
def test_normalize_number(raw, expected):
    from app.services.phone import normalize_number

    assert normalize_number(raw) == expected


def test_send_sms_normalizes_and_returns_failure_on_sdk_error(monkeypatch):
    from africastalking.Service import AfricasTalkingException

    sdk = ModuleType("africastalking")
    sdk.initialize = Mock()
    sdk.SMS = SimpleNamespace(send=Mock(side_effect=AfricasTalkingException("blacklisted")))
    monkeypatch.setitem(sys.modules, "africastalking", sdk)
    monkeypatch.setattr(
        at_client_module,
        "settings",
        SimpleNamespace(dry_run=False, at_api_key="k", at_username="sandbox", at_sender_id="AFTKNG"),
    )
    client = AfricaTalkingClient()

    result = client.send_sms("0707274525", "Hi")

    assert result["status"] == "failed"
    assert result["details"] == "blacklisted"
    sdk.SMS.send.assert_called_once_with("Hi", ["+254707274525"], sender_id="AFTKNG")


def test_summarize_sms_response_flags_rejected_recipients():
    from app.services.at_client import summarize_sms_response

    rejected = {"SMSMessageData": {"Message": "Sent to 0/1", "Recipients": [
        {"statusCode": 403, "status": "InvalidPhoneNumber", "number": "+2547", "messageId": "None"}]}}
    assert summarize_sms_response(rejected)["status"] == "failed"
    assert summarize_sms_response(rejected)["at_status"] == "InvalidPhoneNumber"
    assert summarize_sms_response({"SMSMessageData": {"Message": "InvalidSenderId", "Recipients": []}}) == {
        "status": "failed", "error": "InvalidSenderId",
        "raw": {"SMSMessageData": {"Message": "InvalidSenderId", "Recipients": []}},
    }


def _live_client(monkeypatch, send):
    sdk = ModuleType("africastalking")
    sdk.initialize = Mock()
    sdk.SMS = SimpleNamespace(send=Mock(side_effect=send))
    monkeypatch.setitem(sys.modules, "africastalking", sdk)
    monkeypatch.setattr(
        at_client_module,
        "settings",
        SimpleNamespace(dry_run=False, at_api_key="k", at_username="sandbox", at_sender_id="83107"),
    )
    monkeypatch.setattr(at_client_module.time, "sleep", lambda _: None)
    return AfricaTalkingClient(), sdk


OK = {"SMSMessageData": {"Recipients": [{"statusCode": 101, "status": "Success", "messageId": "ATXid_ok"}]}}
BAD_SENDER = {"SMSMessageData": {"Message": "InvalidSenderId", "Recipients": []}}


def test_invalid_sender_is_retried(monkeypatch):
    replies = iter([BAD_SENDER, OK])
    client, sdk = _live_client(monkeypatch, lambda *a, **k: next(replies))
    result = client.send_sms("+254711731098", "Hi")
    assert result["status"] == "sent"
    assert "sender_fallback" not in result
    assert sdk.SMS.send.call_count == 2


def test_invalid_sender_falls_back_to_default_sender(monkeypatch):
    client, sdk = _live_client(monkeypatch, lambda *a, **k: OK if "sender_id" not in k else BAD_SENDER)
    result = client.send_sms("+254711731098", "Hi")
    assert result["status"] == "sent"
    assert result["sender_fallback"] is True
    assert sdk.SMS.send.call_args.kwargs == {}
