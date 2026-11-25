from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4


class PaymentService(Protocol):
    def pay_sponsor_fee(self, phone: str | None, amount: int, currency: str, reference: str) -> dict:
        """Return the payment provider response for a sponsor fee payment."""


@dataclass
class MockPaymentService:
    def pay_sponsor_fee(self, phone: str | None, amount: int, currency: str, reference: str) -> dict:
        return {
            "status": "mocked",
            "transaction_id": f"DEMO-{uuid4().hex[:10].upper()}",
            "amount": amount,
            "currency": currency,
            "reference": reference,
        }


payment_service: PaymentService = MockPaymentService()
