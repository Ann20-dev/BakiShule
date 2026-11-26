import logging
import time
from typing import Any

from africastalking.Service import AfricasTalkingException
from requests import RequestException

from app.config import settings
from app.services.phone import normalize_number

logger = logging.getLogger(__name__)


SMS_SUCCESS_CODES = {100, 101, 102}  # Processed, Sent, Queued


def summarize_sms_response(response: Any) -> dict:
    """Turn AT's SMS reply into {status, message_id, cost, at_status, raw}.

    AT replies like {"SMSMessageData": {"Message": "Sent to 1/1 ...",
    "Recipients": [{"statusCode": 101, "status": "Success", "messageId": "ATXid_..", ...}]}}.
    """
    if not isinstance(response, dict):
        return {"status": "submitted", "raw": str(response)}
    recipients = (response.get("SMSMessageData") or {}).get("Recipients") or []
    if not recipients:
        message = (response.get("SMSMessageData") or {}).get("Message", "")
        return {"status": "failed", "error": message or "No recipients accepted", "raw": response}
    first = recipients[0]
    ok = first.get("statusCode") in SMS_SUCCESS_CODES
    return {
        "status": "sent" if ok else "failed",
        "message_id": first.get("messageId"),
        "cost": first.get("cost"),
        "at_status": first.get("status"),
        "raw": response,
    }


class AfricaTalkingClient:
    def __init__(self) -> None:
        self._sdk: Any = None
        if not settings.dry_run:
            if not settings.at_api_key:
                raise RuntimeError("AT_API_KEY is required when DRY_RUN=false")
            import africastalking

            africastalking.initialize(settings.at_username, settings.at_api_key)
            self._sdk = africastalking

    def send_sms(self, phone: str, message: str) -> dict:
        phone = normalize_number(phone)
        if settings.dry_run:
            logger.info("DRY_RUN SMS to %s: %s", phone, message)
            return {"status": "mocked", "dry_run": True}
        sender = settings.at_sender_id or None
        result = self._send_once(phone, message, sender)
        # AT sometimes rejects a valid (newly created) shortcode intermittently.
        # Retry, then fall back to AT's default sender so the message still arrives.
        retries = 2
        while sender and result.get("error") == "InvalidSenderId" and retries:
            retries -= 1
            time.sleep(0.5)
            result = self._send_once(phone, message, sender)
        if sender and result.get("error") == "InvalidSenderId":
            logger.warning("Sender %s rejected; sending %s from AT default sender", sender, phone)
            result = {**self._send_once(phone, message, None), "sender_fallback": True}
        return result

    def _send_once(self, phone: str, message: str, sender: str | None) -> dict:
        service = self._sdk.SMS
        try:
            if sender:
                response = service.send(message, [phone], sender_id=sender)
            else:
                response = service.send(message, [phone])
        except (AfricasTalkingException, RequestException, ValueError) as error:
            logger.warning("SMS to %s failed: %s", phone, error)
            return {"status": "failed", "error": "SMS delivery failed", "details": str(error)}
        return summarize_sms_response(response)

    def send_airtime(self, phone: str, amount: int, currency_code: str = "KES") -> dict:
        if settings.dry_run:
            logger.info("DRY_RUN airtime to %s: %s %s", phone, currency_code, amount)
            return {"status": "mocked", "dry_run": True}
        return self._sdk.Airtime.send(
            phone_number=phone,
            amount=str(amount),
            currency_code=currency_code,
        )

    def send_mobile_data(self, product_name: str, phone: str, quantity: float, unit: str, validity: str) -> dict:
        if settings.dry_run:
            logger.info("DRY_RUN mobile data to %s: %s %s", phone, quantity, unit)
            return {"status": "mocked", "dry_run": True}
        return self._sdk.MobileData.send(
            product_name,
            [{
                "phoneNumber": phone,
                "quantity": quantity,
                "unit": unit,
                "validity": validity,
            }],
        )


at_client = AfricaTalkingClient()
