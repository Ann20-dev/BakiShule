from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models import DemoState


def demo_today(db: Session) -> date:
    if not settings.demo_mode:
        return date.today()
    state = db.get(DemoState, "day_offset")
    offset = int(state.value) if state else 0
    return date.today() + timedelta(days=offset)
