from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Intervention, Learner, ParentReply, utc_now_naive
from app.services.clock import demo_today
from app.services.escalation import _log_send, maybe_escalate
from app.services.phone import normalize_number
from app.services.risk import recompute_learner

router = APIRouter()


def _teacher_message(db: Session, learner: Learner, message: str, reason: str) -> None:
    _log_send(
        db,
        learner,
        "staff_alert",
        learner.classroom.teacher.phone,
        message[:155],
        {"category": reason},
    )


def handle_inbound_sms(db: Session, sender: str, raw_text: str) -> int:
    text = raw_text.strip()
    normalized = text.upper()
    learners = list(db.scalars(select(Learner).where(Learner.guardian_phone == sender)))
    if not learners:
        return 0

    if normalized in {"STOP", "START"}:
        for learner in learners:
            learner.sms_opt_out = normalized == "STOP"
            db.add(
                ParentReply(
                    learner_id=learner.id,
                    phone=sender,
                    code=None,
                    raw_text=text,
                )
            )
        db.commit()
        return len(learners)

    code = int(text) if text in {"1", "2", "3"} else None
    for learner in learners:
        db.add(
            ParentReply(
                learner_id=learner.id,
                phone=sender,
                code=code,
                raw_text=text,
            )
        )
    db.flush()

    for learner in learners:
        if code == 1:
            _teacher_message(
                db,
                learner,
                f"Parent reports {learner.name} is sick. Please follow up.",
                "parent_sick_reply",
            )
        elif code == 2:
            snapshot, previous_level = recompute_learner(db, learner, demo_today(db))
            maybe_escalate(db, learner, snapshot, previous_level)
            recent_flag = db.scalars(
                select(Intervention).where(
                    Intervention.learner_id == learner.id,
                    Intervention.type == "sponsor_flag",
                    Intervention.created_at >= utc_now_naive() - timedelta(days=7),
                )
            )
            if not any(item.metadata_json.get("reason") == "parent_fees" for item in recent_flag):
                db.add(
                    Intervention(
                        learner_id=learner.id,
                        type="sponsor_flag",
                        status="open",
                        metadata_json={
                            "reason": "parent_fees",
                            "need": "Fees support requested by guardian",
                            "parent_reply": text,
                        },
                    )
                )
                db.commit()
        else:
            _teacher_message(
                db,
                learner,
                f"Parent reply about {learner.name}: {text[:90]}",
                "parent_other_reply",
            )
    db.commit()
    return len(learners)


@router.post("/sms/inbound")
async def inbound_sms_callback(request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    form = await request.form()
    sender = normalize_number(str(form.get("from", "")))
    raw_text = str(form.get("text", ""))
    handle_inbound_sms(db, sender, raw_text)
    return {"status": "ok"}
