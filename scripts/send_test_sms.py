"""Send one SMS through Africa's Talking to check your credentials.

Usage:
    .venv/bin/python -m scripts.send_test_sms 0707274525 "Hello from BakiShule"

Respects DRY_RUN: set DRY_RUN=false in .env to actually send.
"""
import json
import sys

from app.config import settings
from app.services.at_client import at_client


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    phone = sys.argv[1]
    message = sys.argv[2] if len(sys.argv) > 2 else "Hello from BakiShule!"
    print(f"username={settings.at_username} sender_id={settings.at_sender_id or '(default)'} dry_run={settings.dry_run}")
    result = at_client.send_sms(phone, message)
    print(json.dumps(result, indent=2, default=str))
    return 1 if result.get("status") == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
