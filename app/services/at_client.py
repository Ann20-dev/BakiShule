import logging
from typing import Any

from africastalking.Service import AfricasTalkingException
from requests import RequestException

from app.config import settings
from app.services.phone import normalize_number

logger = logging.getLogger(__name__)


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
        service = self._sdk.SMS
        try:
            if settings.at_sender_id:
                response = service.send(message, [phone], sender_id=settings.at_sender_id)
            else:
                response = service.send(message, [phone])
        except (AfricasTalkingException, RequestException, ValueError) as error:
            logger.warning("SMS to %s failed: %s", phone, error)
            return {"status": "failed", "error": "SMS delivery failed", "details": str(error)}
        if not isinstance(response, dict):
            return {"status": "submitted", "raw": str(response)}
        return response

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
