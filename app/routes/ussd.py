import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AttendanceRecord, ClassRoom, RiskSnapshot, Teacher
from app.services.attendance import save_class_attendance
from app.services.clock import demo_today
from app.services.phone import normalize_number

router = APIRouter()


def _class_selection(classes: list[ClassRoom], action: str) -> str:
    lines = [f"CON Select class for {action}:"]
    lines.extend(f"{index}. {room.name}" for index, room in enumerate(classes, start=1))
    return "\n".join(lines)


def handle_ussd(db: Session, phone_number: str, text: str) -> str:
    teacher = db.scalar(select(Teacher).where(Teacher.phone == normalize_number(phone_number)))
    if not teacher:
        return "END Number not registered. Contact your school admin."

    classes = list(teacher.classrooms)
    if not classes:
        return "END No class is assigned to this number."
    parts = text.split("*") if text else []
    if not parts:
        return "CON BakiShule\n1. Mark attendance\n2. Class summary\n3. At-risk learners"

    action = parts[0]
    if action not in {"1", "2", "3"}:
        return "END Invalid choice. Dial again."

    class_part = parts[1] if len(parts) > 1 else ""
    classroom: ClassRoom | None = None
    if class_part:
        if class_part.isdigit() and 1 <= int(class_part) <= len(classes):
            classroom = classes[int(class_part) - 1]
        else:
            return "END Invalid class choice. Dial again."

    if action == "1":
        if not classroom:
            return _class_selection(classes, "attendance")
        if len(parts) == 2:
            return "CON Enter absent roll numbers (space/comma separated). 0 if none."
        if len(parts) == 3:
            absent_input = parts[2].strip()
            if not absent_input:
                return "CON Enter absent roll numbers, or 0 if none."
            tokens = [] if absent_input == "0" else re.split(r"[\s,]+", absent_input)
            roll_numbers = {token for token in tokens if token}
            learners_by_roll = {learner.roll_number: learner for learner in classroom.learners}
            invalid = sorted(roll_numbers - learners_by_roll.keys())
            if invalid:
                return f"CON Unknown roll: {', '.join(invalid)[:60]}. Enter absent rolls again."
            absent_names = [learners_by_roll[roll].name for roll in sorted(roll_numbers)]
            names = ", ".join(absent_names[:4]) or "None"
            if len(absent_names) > 4:
                names += f" +{len(absent_names) - 4} more"
            return f"CON Absent: {names}. Others present. Reply 1 to save, 0 cancel."
        if len(parts) == 4 and parts[3] in {"0", "1"}:
            if parts[3] == "0":
                return "END Attendance cancelled."
            absent_input = parts[2].strip()
            absent_rolls = set() if absent_input == "0" else set(
                token for token in re.split(r"[\s,]+", absent_input) if token
            )
            try:
                count = save_class_attendance(db, classroom, absent_rolls)
            except ValueError:
                return "END Invalid roll number. No attendance saved."
            return f"END Saved attendance for {count} learners in {classroom.name}."
        return "END Invalid attendance entry. Dial again."

    if not classroom:
        return _class_selection(classes, "summary" if action == "2" else "at-risk")

    if action == "2":
        today = demo_today(db)
        week_start = today - timedelta(days=today.weekday())
        records = list(
            db.scalars(
                select(AttendanceRecord).where(
                    AttendanceRecord.learner_id.in_([learner.id for learner in classroom.learners]),
                    AttendanceRecord.date >= week_start,
                    AttendanceRecord.date <= today,
                )
            )
        )
        present = sum(record.present for record in records if record.date == today)
        absent = sum(not record.present for record in records if record.date == today)
        weekly_percentage = round(sum(record.present for record in records) / len(records) * 100) if records else 0
        return f"END {classroom.name} today: {present} present, {absent} absent. Week: {weekly_percentage}%."

    learner_ids = [learner.id for learner in classroom.learners]
    snapshots = list(
        db.scalars(
            select(RiskSnapshot)
            .where(RiskSnapshot.learner_id.in_(learner_ids))
            .order_by(RiskSnapshot.date.desc(), RiskSnapshot.score.desc())
        )
    )
    latest: dict[int, RiskSnapshot] = {}
    for snapshot in snapshots:
        latest.setdefault(snapshot.learner_id, snapshot)
    top = sorted(latest.values(), key=lambda item: item.score, reverse=True)[:5]
    if not top:
        return f"END No risk scores yet for {classroom.name}."
    lines = [f"{item.learner.roll_number} {item.learner.name[:12]}:{item.level}" for item in top]
    return f"END {classroom.name} at-risk: " + "; ".join(lines)


@router.post("/ussd", response_class=PlainTextResponse)
async def ussd_callback(request: Request, db: Session = Depends(get_db)) -> str:
    form = await request.form()
    return handle_ussd(db, str(form.get("phoneNumber", "")), str(form.get("text", "")))
