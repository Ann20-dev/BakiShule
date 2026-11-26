from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db import Base


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class School(Base):
    __tablename__ = "schools"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    county: Mapped[str] = mapped_column(String(80))
    classrooms: Mapped[list["ClassRoom"]] = relationship(back_populates="school", cascade="all, delete-orphan")


class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(24), default="teacher")
    language: Mapped[str | None] = mapped_column(String(2), nullable=True)  # en | sw, null until chosen
    classrooms: Mapped[list["ClassRoom"]] = relationship(back_populates="teacher")


class ClassRoom(Base):
    __tablename__ = "classrooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"))
    name: Mapped[str] = mapped_column(String(40))
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"))
    school: Mapped[School] = relationship(back_populates="classrooms")
    teacher: Mapped[Teacher] = relationship(back_populates="classrooms")
    learners: Mapped[list["Learner"]] = relationship(back_populates="classroom", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("school_id", "name"),)


class Learner(Base):
    __tablename__ = "learners"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    roll_number: Mapped[str] = mapped_column(String(20))
    classroom_id: Mapped[int] = mapped_column(ForeignKey("classrooms.id"), index=True)
    gender: Mapped[str] = mapped_column(String(20))
    guardian_name: Mapped[str] = mapped_column(String(120))
    guardian_phone: Mapped[str] = mapped_column(String(24), index=True)
    sponsor_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    sms_opt_out: Mapped[bool] = mapped_column(Boolean, default=False)
    ever_watch: Mapped[bool] = mapped_column(Boolean, default=False)
    classroom: Mapped[ClassRoom] = relationship(back_populates="learners")
    attendance: Mapped[list["AttendanceRecord"]] = relationship(back_populates="learner", cascade="all, delete-orphan")
    replies: Mapped[list["ParentReply"]] = relationship(back_populates="learner", cascade="all, delete-orphan")
    risks: Mapped[list["RiskSnapshot"]] = relationship(back_populates="learner", cascade="all, delete-orphan")
    interventions: Mapped[list["Intervention"]] = relationship(back_populates="learner", cascade="all, delete-orphan")
    behaviour_logs: Mapped[list["BehaviourLog"]] = relationship(back_populates="learner", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("classroom_id", "roll_number"),)


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    learner_id: Mapped[int] = mapped_column(ForeignKey("learners.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    present: Mapped[bool] = mapped_column(Boolean)
    learner: Mapped[Learner] = relationship(back_populates="attendance")
    __table_args__ = (UniqueConstraint("learner_id", "date"),)


class ParentReply(Base):
    __tablename__ = "parent_replies"

    id: Mapped[int] = mapped_column(primary_key=True)
    learner_id: Mapped[int] = mapped_column(ForeignKey("learners.id"), index=True)
    phone: Mapped[str] = mapped_column(String(24))
    code: Mapped[int | None] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)
    learner: Mapped[Learner] = relationship(back_populates="replies")


class RiskSnapshot(Base):
    __tablename__ = "risk_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    learner_id: Mapped[int] = mapped_column(ForeignKey("learners.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    score: Mapped[int] = mapped_column(Integer)
    level: Mapped[str] = mapped_column(String(20), index=True)
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    learner: Mapped[Learner] = relationship(back_populates="risks")
    __table_args__ = (UniqueConstraint("learner_id", "date"),)


class Intervention(Base):
    __tablename__ = "interventions"

    id: Mapped[int] = mapped_column(primary_key=True)
    learner_id: Mapped[int] = mapped_column(ForeignKey("learners.id"), index=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="created")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, index=True)
    learner: Mapped[Learner] = relationship(back_populates="interventions")


class Sponsor(Base):
    __tablename__ = "sponsors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(24))
    email: Mapped[str | None] = mapped_column(String(160))


class DemoState(Base):
    __tablename__ = "demo_state"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(String(120))


class BehaviourLog(Base):
    """A behaviour note logged by a teacher over USSD. Codes live in app/school_config.py."""

    __tablename__ = "behaviour_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    learner_id: Mapped[int] = mapped_column(ForeignKey("learners.id"), index=True)
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id"), nullable=True)
    code: Mapped[int] = mapped_column(Integer)
    sentiment: Mapped[str] = mapped_column(String(10), index=True)  # positive | concern
    subject: Mapped[str | None] = mapped_column(String(40), nullable=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, index=True)
    learner: Mapped[Learner] = relationship(back_populates="behaviour_logs")
    teacher: Mapped[Teacher | None] = relationship()


class GuardianAccount(Base):
    """Per-phone guardian settings: hashed PIN, lockout state, preferred language."""

    __tablename__ = "guardian_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    pin_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pin_salt: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failed_pin_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    language: Mapped[str | None] = mapped_column(String(2), nullable=True)  # en | sw, null until chosen


class MessageLog(Base):
    """One parent exchange (inbound command and/or automatic reply), shown live on the dashboard."""

    __tablename__ = "message_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(24), index=True)
    channel: Mapped[str] = mapped_column(String(8), default="sms")  # sms | ussd
    command: Mapped[str | None] = mapped_column(String(20), nullable=True)
    language: Mapped[str | None] = mapped_column(String(2), nullable=True)  # null = bilingual reply
    inbound_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # PINs are masked
    reply_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="ok")
    counted: Mapped[bool] = mapped_column(Boolean, default=False)  # counts toward the daily limit
    learner_id: Mapped[int | None] = mapped_column(ForeignKey("learners.id"), nullable=True, index=True)
    delivery_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    at_response: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, index=True)
    learner: Mapped[Learner | None] = relationship()
