import argparse
import random
from datetime import date, timedelta

from sqlalchemy import select

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.models import AttendanceRecord, ClassRoom, Learner, School, Teacher
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
        recompute_all(db, escalate_transitions=False)
        print(f"Seeded {len(classes)} classes, {len(learners)} learners, {len(records)} attendance records.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed BakiShule demo data.")
    parser.add_argument("--reset", action="store_true", help="drop and recreate the demo database")
    seed(reset=parser.parse_args().reset)
