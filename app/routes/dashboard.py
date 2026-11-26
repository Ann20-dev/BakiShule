from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, engine, get_db
from app.models import (
    AttendanceRecord, BehaviourLog, ClassRoom, DemoState, Intervention, Learner, MessageLog, ParentReply, RiskSnapshot,
    Teacher,
)
from app.services.clock import demo_today
from app.messages import behaviour_label, normalize_language, t
from app.services.escalation import _log_send, guardian_reply_language, maybe_escalate
from app.services.payments import payment_service
from app.services.risk import recompute_all, recompute_learner
from app.services.language import guardian_language
from app.services.parent_queries import get_account, reset_language
from app.services.weekly_reports import run_weekly_reports_job

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _latest_risks(db: Session) -> dict[int, RiskSnapshot]:
    latest: dict[int, RiskSnapshot] = {}
    for snapshot in db.scalars(select(RiskSnapshot).order_by(RiskSnapshot.date.desc(), RiskSnapshot.id.desc())):
        latest.setdefault(snapshot.learner_id, snapshot)
    return latest


def _overview_data(db: Session) -> dict:
    today = demo_today(db)
    learners = list(db.scalars(select(Learner).order_by(Learner.id)))
    latest = _latest_risks(db)
    risk_counts = Counter(snapshot.level for snapshot in latest.values())
    learner_priority = {"critical": 0, "at_risk": 1, "watch": 2, "green": 3}
    learners.sort(
        key=lambda learner: (
            learner_priority.get(latest.get(learner.id).level, 4) if latest.get(learner.id) else 4,
            learner.name,
        )
    )

    trend_labels: list[str] = []
    trend_rates: list[float] = []
    for offset in range(29, -1, -1):
        day = today - timedelta(days=offset)
        records = list(db.scalars(select(AttendanceRecord).where(AttendanceRecord.date == day)))
        if records:
            trend_labels.append(day.strftime("%b %d"))
            trend_rates.append(round(sum(record.present for record in records) / len(records) * 100, 1))

    dates = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    classes = list(db.scalars(select(ClassRoom).order_by(ClassRoom.name)))
    heatmap = []
    for classroom in classes:
        rows = []
        learner_ids = [learner.id for learner in classroom.learners]
        for day in dates:
            records = list(
                db.scalars(
                    select(AttendanceRecord).where(
                        AttendanceRecord.learner_id.in_(learner_ids),
                        AttendanceRecord.date == day,
                    )
                )
            ) if learner_ids else []
            rows.append(round(sum(record.present for record in records) / len(records) * 100) if records else None)
        heatmap.append({"classroom": classroom.name, "values": rows})

    todays_records = list(db.scalars(select(AttendanceRecord).where(AttendanceRecord.date == today)))
    present_count = sum(record.present for record in todays_records)
    attendance_rate = round(present_count / len(todays_records) * 100) if todays_records else 0
    return {
        "today": today,
        "learner_count": len(learners),
        "attendance_rate": attendance_rate,
        "risk_counts": {level: risk_counts.get(level, 0) for level in ("green", "watch", "at_risk", "critical")},
        "trend_labels": trend_labels,
        "trend_rates": trend_rates,
        "heatmap": heatmap,
        "dates": dates,
        "demo_mode": settings.demo_mode,
        "learners": learners,
    }


@router.get("/")
def overview(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="overview.html",
        context=_overview_data(db),
    )


@router.get("/partials/summary")
def summary_partial(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="summary_partial.html",
        context=_overview_data(db),
    )


@router.get("/at-risk")
def at_risk_list(request: Request, sort: str = "score", db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="at_risk.html",
        context={"sort": sort, "rows": _at_risk_rows(db, sort)},
    )


@router.get("/partials/at-risk")
def at_risk_partial(request: Request, sort: str = "score", db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="at_risk_table.html",
        context={"rows": _at_risk_rows(db, sort), "sort": sort},
    )


def _at_risk_rows(db: Session, sort: str) -> list[dict]:
    latest = _latest_risks(db)
    rows = [
        {"learner": db.get(Learner, learner_id), "snapshot": snapshot}
        for learner_id, snapshot in latest.items()
        if snapshot.level != "green"
    ]
    if sort == "name":
        rows.sort(key=lambda row: row["learner"].name.lower())
    elif sort == "class":
        rows.sort(key=lambda row: (row["learner"].classroom.name, -row["snapshot"].score))
    else:
        rows.sort(key=lambda row: row["snapshot"].score, reverse=True)
    return rows


@router.get("/learners/{learner_id}")
def learner_detail(learner_id: int, request: Request, db: Session = Depends(get_db)):
    learner = db.get(Learner, learner_id)
    if not learner:
        raise HTTPException(status_code=404, detail="Learner not found")
    attendance = list(
        db.scalars(
            select(AttendanceRecord)
            .where(AttendanceRecord.learner_id == learner_id)
            .order_by(AttendanceRecord.date.desc())
            .limit(60)
        )
    )
    risks = list(
        db.scalars(
            select(RiskSnapshot)
            .where(RiskSnapshot.learner_id == learner_id)
            .order_by(RiskSnapshot.date.desc())
            .limit(60)
        )
    )
    risks.reverse()
    replies = list(
        db.scalars(
            select(ParentReply)
            .where(ParentReply.learner_id == learner_id)
            .order_by(ParentReply.received_at.desc())
            .limit(10)
        )
    )
    interventions = list(
        db.scalars(
            select(Intervention)
            .where(Intervention.learner_id == learner_id)
            .order_by(Intervention.created_at.desc())
            .limit(30)
        )
    )
    behaviour = list(
        db.scalars(
            select(BehaviourLog)
            .where(BehaviourLog.learner_id == learner_id)
            .order_by(BehaviourLog.date.desc(), BehaviourLog.id.desc())
            .limit(30)
        )
    )
    timeline = [{"kind": "intervention", "at": item.created_at, "item": item} for item in interventions]
    timeline += [
        {
            "kind": "behaviour",
            "at": datetime.combine(log.date, log.created_at.time()),
            "item": log,
            "label": behaviour_label(log.code, "en"),
        }
        for log in behaviour
    ]
    timeline.sort(key=lambda entry: entry["at"], reverse=True)
    return templates.TemplateResponse(
        request=request,
        name="learner.html",
        context={
            "learner": learner,
            "guardian_language": guardian_language(db, learner.guardian_phone),
            "languages": LANGUAGE_LABELS,
            "attendance": attendance,
            "risks": risks,
            "replies": replies,
            "interventions": interventions,
            "behaviour": behaviour,
            "timeline": timeline[:40],
        },
    )


LANGUAGE_LABELS = {"en": "English", "sw": "Kiswahili"}


@router.post("/guardians/language")
def update_guardian_language(
    phone: str = Form(...), language: str = Form(...), back: str = Form("/"), db: Session = Depends(get_db)
):
    account = get_account(db, phone, create=True)
    account.language = language if language in LANGUAGE_LABELS else None
    db.commit()
    return RedirectResponse(back if back.startswith("/") else "/", status_code=303)


@router.get("/teachers")
def teachers_page(request: Request, db: Session = Depends(get_db)):
    teachers = list(db.scalars(select(Teacher).order_by(Teacher.name)))
    return templates.TemplateResponse(
        request=request, name="teachers.html", context={"teachers": teachers, "languages": LANGUAGE_LABELS}
    )


@router.post("/teachers/{teacher_id}/language")
def update_teacher_language(teacher_id: int, language: str = Form(...), db: Session = Depends(get_db)):
    teacher = db.get(Teacher, teacher_id)
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    teacher.language = language if language in LANGUAGE_LABELS else None
    db.commit()
    return RedirectResponse("/teachers", status_code=303)


def _mask_phone(phone: str) -> str:
    return f"{phone[:6]}***{phone[-3:]}" if phone and len(phone) > 9 else phone


def _parent_query_rows(db: Session, limit: int = 20) -> list[dict]:
    logs = list(db.scalars(select(MessageLog).order_by(MessageLog.id.desc()).limit(limit)))
    return [{"log": log, "phone": _mask_phone(log.phone)} for log in logs]


@router.get("/parent-queries")
def parent_queries_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request=request, name="parent_queries.html", context={"rows": _parent_query_rows(db, 50), "full": True}
    )


@router.get("/partials/parent-queries")
def parent_queries_partial(request: Request, limit: int = 12, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="parent_queries_panel.html",
        context={"rows": _parent_query_rows(db, min(limit, 100))},
    )


@router.get("/sponsors")
def sponsor_view(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="sponsors.html",
        context={"profiles": _sponsor_profiles(db)},
    )


@router.get("/partials/sponsors")
def sponsor_partial(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="sponsor_cards.html",
        context={"profiles": _sponsor_profiles(db)},
    )


def _sponsor_profiles(db: Session) -> list[dict]:
    latest = _latest_risks(db)
    flags = list(
        db.scalars(
            select(Intervention)
            .where(Intervention.type == "sponsor_flag", Intervention.status == "open")
            .order_by(Intervention.created_at.desc())
        )
    )
    seen: set[int] = set()
    profiles = []
    for flag in flags:
        learner = flag.learner
        if learner.id in seen:
            continue
        seen.add(learner.id)
        snapshot = latest.get(learner.id)
        fee_request = flag.metadata_json.get("reason") == "parent_fees"
        if not fee_request and (not snapshot or snapshot.level not in {"at_risk", "critical"}):
            continue
        consent_name = learner.name if learner.sponsor_consent else f"{learner.name[0]}. (anonymised)"
        profiles.append(
            {
                "id": learner.id,
                "name": consent_name,
                "classroom": learner.classroom.name,
                "county": learner.classroom.school.county,
                "need": flag.metadata_json.get("need", "Attendance and fee support"),
                "score": snapshot.score if snapshot else None,
                "consented": learner.sponsor_consent,
            }
        )
    return profiles


@router.post("/sponsors/{learner_id}/pay")
def sponsor_pay(learner_id: int, db: Session = Depends(get_db)):
    learner = db.get(Learner, learner_id)
    if not learner:
        raise HTTPException(status_code=404, detail="Learner not found")
    open_flag = db.scalar(
        select(Intervention.id).where(
            Intervention.learner_id == learner_id,
            Intervention.type == "sponsor_flag",
            Intervention.status == "open",
        ).limit(1)
    )
    if not open_flag:
        raise HTTPException(status_code=409, detail="Learner has no open sponsor flag")

    response = payment_service.pay_sponsor_fee(
        phone=None,
        amount=3000,
        currency="KES",
        reference=f"learner-{learner_id}",
    )
    db.add(
        Intervention(
            learner_id=learner_id,
            type="fee_payment",
            status=response.get("status", "completed"),
            metadata_json={"payment_response": response, "amount": 3000, "currency": "KES"},
        )
    )
    db.commit()
    # Receipts go to the guardian, class teacher and head teacher(s), each in their own language.
    recipients = {learner.guardian_phone: guardian_reply_language(db, learner.guardian_phone)}
    staff = [learner.classroom.teacher, *db.scalars(
        select(Teacher).join(Teacher.classrooms).where(
            Teacher.role == "head_teacher",
            ClassRoom.school_id == learner.classroom.school_id,
        )
    )]
    for teacher in staff:
        recipients.setdefault(teacher.phone, normalize_language(teacher.language))
    for phone, lang in recipients.items():
        _log_send(
            db,
            learner,
            "fee_payment",
            phone,
            t("sponsor_receipt", lang, amount="3,000", name=learner.name),
            {"payment_response": response},
        )
    for flag in db.scalars(
        select(Intervention).where(
            Intervention.learner_id == learner_id,
            Intervention.type == "sponsor_flag",
            Intervention.status == "open",
        )
    ):
        flag.status = "supported"
    db.commit()
    return RedirectResponse("/sponsors", status_code=303)


def _require_demo_mode() -> None:
    if not settings.demo_mode:
        raise HTTPException(status_code=404, detail="Demo controls are disabled")


@router.post("/demo/advance")
def advance_demo_day(db: Session = Depends(get_db)):
    _require_demo_mode()
    state = db.get(DemoState, "day_offset")
    if state:
        state.value = str(int(state.value) + 1)
    else:
        db.add(DemoState(key="day_offset", value="1"))
    db.commit()
    recompute_all(db, demo_today(db))
    return RedirectResponse("/", status_code=303)


@router.post("/demo/recompute")
def recompute_demo_risks(db: Session = Depends(get_db)):
    _require_demo_mode()
    recompute_all(db, demo_today(db))
    return RedirectResponse("/", status_code=303)


@router.post("/demo/streak")
def simulate_streak(learner_id: int = Form(...), db: Session = Depends(get_db)):
    _require_demo_mode()
    learner = db.get(Learner, learner_id)
    if not learner:
        raise HTTPException(status_code=404, detail="Learner not found")
    today = demo_today(db)
    for offset in range(28):
        day = today - timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        record = db.scalar(
            select(AttendanceRecord).where(
                AttendanceRecord.learner_id == learner_id,
                AttendanceRecord.date == day,
            )
        )
        if record:
            record.present = True
        else:
            db.add(AttendanceRecord(learner_id=learner_id, date=day, present=True))
    db.flush()
    snapshot, previous_level = recompute_learner(db, learner, today)
    db.commit()
    maybe_escalate(db, learner, snapshot, previous_level)
    return RedirectResponse(f"/learners/{learner_id}", status_code=303)


@router.post("/demo/weekly-reports")
def send_weekly_reports_now(background_tasks: BackgroundTasks):
    _require_demo_mode()
    background_tasks.add_task(run_weekly_reports_job)
    return RedirectResponse("/?weekly=sent", status_code=303)


@router.post("/demo/reset-language")
def reset_demo_guardian_language(db: Session = Depends(get_db)):
    """Forget the demo guardian's language so the first-time language screen shows again."""
    _require_demo_mode()
    reset_language(db, settings.demo_parent_phone)
    return RedirectResponse("/?language=reset", status_code=303)


@router.post("/demo/reset")
def reset_demo_data():
    _require_demo_mode()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    from scripts.seed import seed

    seed()
    return RedirectResponse("/", status_code=303)
