import argparse
import random
from datetime import date, timedelta

from sqlalchemy import select

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.models import AttendanceRecord, BehaviourLog, ClassRoom, GuardianAccount, Learner, School, Teacher
from app.school_config import BEHAVIOUR_CODES, SUBJECTS
from app.services.risk import recompute_all


def seed(reset: bool = False) -> None:
    Base.metadata.create_all(bind=engine)
    if reset:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        if db.scalar(select(School.id).limit(1)):
            print("Seed data already exists. Use --reset to recreate it.")
            return

        school = School(name="Baki Shule Primary", county="Nairobi")
        db.add(school)
        teachers = [
            Teacher(name="Amina Otieno", phone=settings.demo_teacher_phone, role="teacher"),
            Teacher(name="Peter Kamau", phone="+254700000003", role="teacher"),
            Teacher(name="Grace Wanjiku", phone="+254700000004", role="head_teacher"),
        ]
        db.add_all(teachers)
        db.flush()
        classes = [
            ClassRoom(name="5A", school=school, teacher=teachers[0]),
            ClassRoom(name="5B", school=school, teacher=teachers[1]),
            ClassRoom(name="6A", school=school, teacher=teachers[2]),
        ]
        db.add_all(classes)
        db.flush()

        learners: list[Learner] = []
        for class_index, classroom in enumerate(classes):
            for number in range(1, 31):
                position = class_index * 30 + number
                guardian_phone = settings.demo_parent_phone if position == 1 else f"+254711{position:06d}"
                learners.append(
                    Learner(
                        name=f"Learner {position:02d}",
                        roll_number=f"{number:02d}",
                        classroom=classroom,
                        gender="female" if position % 2 else "male",
                        guardian_name=f"Guardian {position:02d}",
                        guardian_phone=guardian_phone,
                        sponsor_consent=position in {2, 3},
                    )
                )
        # Two learners share a guardian and are absent together in the seeded pattern.
        learners[30].guardian_phone = learners[31].guardian_phone
        learners[30].guardian_name = learners[31].guardian_name = "Shared Guardian"
        db.add_all(learners)
        db.flush()

        today = date.today()
        rng = random.Random(2026)
        recent_absence_days = set()
        offset = 1
        while len(recent_absence_days) < 2:
            candidate = today - timedelta(days=offset)
            if candidate.weekday() < 5:
                recent_absence_days.add(candidate)
            offset += 1
        records: list[AttendanceRecord] = []
        for learner_index, learner in enumerate(learners):
            for days_ago in range(60, -1, -1):
                day = today - timedelta(days=days_ago)
                if day.weekday() >= 5:
                    continue
                absent = rng.random() < 0.045
                # Clear, explainable patterns for the hackathon demo.
                if learner_index == 0 and day.weekday() == 0:
                    absent = True
                elif learner_index == 6 and day in recent_absence_days:
                    absent = True
                elif learner_index == 1 and days_ago <= 13 and days_ago > 0 and day.weekday() < 5:
                    absent = days_ago % 3 != 0
                elif learner_index == 2 and 28 <= days_ago <= 24:
                    absent = True
                elif learner_index in {30, 31} and days_ago in {20, 12, 4}:
                    absent = True
                elif learner_index == 5 and 0 <= days_ago <= 5 and day.weekday() < 5:
                    absent = True
                records.append(AttendanceRecord(learner=learner, date=day, present=not absent))
        db.add_all(records)
        db.commit()
        added = add_extra_classes(db, teachers[0], today)
        seed_behaviour(db, today)
        ensure_guardian_accounts(db)
        recompute_all(db, escalate_transitions=False)
        print(
            f"Seeded {len(classes) + added} classes, {len(learners) + added * 30} learners, "
            f"{len(records)}+ attendance records."
        )


EXTRA_CLASSES = ["4A", "7A"]


def _last_school_days(today: date, count: int) -> list[date]:
    days, offset = [], 0
    while len(days) < count:
        day = today - timedelta(days=offset)
        if day.weekday() < 5:
            days.append(day)
        offset += 1
    return days


def add_extra_classes(db, teacher: Teacher, today: date | None = None) -> int:
    """Give the demo teacher extra classes (with learners + 60 days of attendance). Idempotent."""
    today = today or date.today()
    school = teacher.classrooms[0].school if teacher.classrooms else db.scalar(select(School).limit(1))
    existing = {room.name for room in db.scalars(select(ClassRoom).where(ClassRoom.school_id == school.id))}
    position = db.query(Learner).count()
    rng = random.Random(2027)
    last4, last6 = set(_last_school_days(today, 4)), set(_last_school_days(today, 6))
    added = 0
    for name in EXTRA_CLASSES:
        if name in existing:
            continue
        classroom = ClassRoom(name=name, school=school, teacher=teacher)
        db.add(classroom)
        for number in range(1, 31):
            position += 1
            learner = Learner(
                name=f"Learner {position:02d}",
                roll_number=f"{number:02d}",
                classroom=classroom,
                gender="female" if position % 2 else "male",
                guardian_name=f"Guardian {position:02d}",
                guardian_phone=(
                    settings.demo_parent_phone if name == EXTRA_CLASSES[0] and number == 1 else f"+254711{position:06d}"
                ),
            )
            db.add(learner)
            for days_ago in range(60, -1, -1):
                day = today - timedelta(days=days_ago)
                if day.weekday() >= 5:
                    continue
                absent = rng.random() < 0.045
                # Demo patterns so the at-risk menus have something to show.
                if number == 3 and day in last4:
                    absent = True  # 4 absences in a row
                elif number == 6 and (day in last6 or (day.weekday() == 0 and days_ago <= 35)):
                    absent = True  # long streak + Monday pattern
                elif number == 11 and day.weekday() == 4:
                    absent = True  # always misses Fridays
                elif number == 17 and 8 <= days_ago <= 20 and days_ago % 2 == 0:
                    absent = True  # recent drop
                db.add(AttendanceRecord(learner=learner, date=day, present=not absent))
        added += 1
    db.commit()
    return added


def seed_behaviour(db, today: date | None = None) -> int:
    """Realistic behaviour notes for the last ~5 weeks. Idempotent (skips if any exist)."""
    today = today or date.today()
    if db.scalar(select(BehaviourLog.id).limit(1)):
        return 0
    rng = random.Random(2028)
    school_days = [today - timedelta(days=offset) for offset in range(0, 36)]
    school_days = [day for day in school_days if day.weekday() < 5]
    positive = [code for code, entry in BEHAVIOUR_CODES.items() if entry["sentiment"] == "positive"]
    concern = [code for code, entry in BEHAVIOUR_CODES.items() if entry["sentiment"] == "concern"]
    logs = []

    def add(learner, code, day, subject=None):
        logs.append(BehaviourLog(
            learner_id=learner.id, teacher_id=learner.classroom.teacher_id, code=code,
            sentiment=BEHAVIOUR_CODES[code]["sentiment"], subject=subject, date=day,
        ))

    for learner in db.scalars(select(Learner).order_by(Learner.id)):
        for _ in range(rng.randint(1, 4)):
            add(learner, rng.choice(positive), rng.choice(school_days), rng.choice([None, *SUBJECTS.values()]))
        for _ in range(rng.choice([0, 0, 0, 1, 1, 2])):
            add(learner, rng.choice(concern), rng.choice(school_days[5:]))

    # Clear demo stories.
    demo_children = list(db.scalars(select(Learner).where(Learner.guardian_phone == settings.demo_parent_phone)))
    recent = school_days[:10]
    for learner in demo_children[:1]:  # the demo parent's first child: a mixed but positive picture
        add(learner, 1, recent[0], "Maths")
        add(learner, 3, recent[1])
        add(learner, 6, recent[3], "Science")
        add(learner, 2, recent[4], "English")
        add(learner, 5, recent[6])
    for learner in db.scalars(select(Learner).where(Learner.roll_number == "04")):
        add(learner, 4, recent[0])  # repeated concerns -> behaviour risk signal
        add(learner, 2, recent[2], "Maths")
        add(learner, 3, recent[4])
    db.add_all(logs)
    db.commit()
    return len(logs)


def ensure_guardian_accounts(db, pin: str | None = None) -> int:
    """Give every guardian phone an account with the demo PIN (hashed). Idempotent."""
    from app.services.parent_queries import hash_pin

    pin = pin or settings.demo_guardian_pin
    existing = {account.phone for account in db.scalars(select(GuardianAccount))}
    phones = {learner.guardian_phone for learner in db.scalars(select(Learner))} - existing
    for phone in sorted(phones):
        digest, salt = hash_pin(pin)
        db.add(GuardianAccount(phone=phone, pin_hash=digest, pin_salt=salt, failed_pin_attempts=0))
    db.commit()
    assign_demo_languages(db)
    return len(phones)


def assign_demo_languages(db) -> None:
    """Demo languages: the demo guardian (and demo teacher, same phone) have none, so the first-time
    language screen shows; other guardians alternate Kiswahili/English; Peter Kamau prefers Kiswahili."""
    for index, account in enumerate(db.scalars(select(GuardianAccount).order_by(GuardianAccount.phone))):
        account.language = None if account.phone == settings.demo_parent_phone else ("sw" if index % 3 == 0 else "en")
    for teacher in db.scalars(select(Teacher)):
        if teacher.phone in {settings.demo_teacher_phone, settings.demo_parent_phone}:
            teacher.language = None
        else:
            teacher.language = "sw" if teacher.name == "Peter Kamau" else "en"
    db.commit()


def upgrade_existing() -> None:
    """Bring an existing demo database up to date without resetting it."""
    from app.services.clock import demo_today

    from app.migrations import sync_schema

    sync_schema(engine)  # new tables and columns
    with SessionLocal() as db:
        today = demo_today(db)
        teacher = db.scalar(select(Teacher).where(Teacher.phone == settings.demo_teacher_phone))
        added = add_extra_classes(db, teacher, today) if teacher else 0
        first_extra = db.scalar(
            select(Learner).join(ClassRoom).where(ClassRoom.name == EXTRA_CLASSES[0], Learner.roll_number == "01")
        )
        if first_extra and first_extra.guardian_phone != settings.demo_parent_phone:
            first_extra.guardian_phone = settings.demo_parent_phone
            db.commit()
        notes = seed_behaviour(db, today)
        accounts = ensure_guardian_accounts(db)
        assign_demo_languages(db)
        recompute_all(db, as_of=today, escalate_transitions=False)
        print(f"Upgrade done: {added} class(es), {notes} behaviour notes, {accounts} guardian account(s).")


def add_classes_to_existing() -> None:
    with SessionLocal() as db:
        teacher = db.scalar(select(Teacher).where(Teacher.phone == settings.demo_teacher_phone))
        if not teacher:
            print(f"No teacher with DEMO_TEACHER_PHONE={settings.demo_teacher_phone}.")
            return
        from app.services.clock import demo_today

        today = demo_today(db)
        added = add_extra_classes(db, teacher, today)
        recompute_all(db, as_of=today, escalate_transitions=False)
        print(f"Added {added} class(es) for {teacher.name}: {', '.join(EXTRA_CLASSES)}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed BakiShule demo data.")
    parser.add_argument("--reset", action="store_true", help="drop and recreate the demo database")
    parser.add_argument(
        "--add-classes", action="store_true", help="add the extra demo classes to an existing database"
    )
    parser.add_argument(
        "--upgrade", action="store_true",
        help="add new tables, extra classes, behaviour notes and guardian PINs to an existing database",
    )
    args = parser.parse_args()
    if args.upgrade:
        upgrade_existing()
    elif args.add_classes:
        add_classes_to_existing()
    else:
        seed(reset=args.reset)
