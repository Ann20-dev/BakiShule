from app.models import AttendanceRecord, ClassRoom, Learner, School, Teacher
from app.routes.ussd import handle_ussd


def build_teacher(db_session):
    school = School(name="Test School", county="Nairobi")
    teacher = Teacher(name="Teacher", phone="+254700123456", language="en")
    classroom = ClassRoom(name="5A", school=school, teacher=teacher)
    learners = [
        Learner(
            name=f"Learner {number}",
            roll_number=f"{number:02d}",
            classroom=classroom,
            gender="female",
            guardian_name="Parent",
            guardian_phone=f"+25471100000{number}",
        )
        for number in range(1, 4)
    ]
    db_session.add_all([school, teacher, classroom, *learners])
    db_session.flush()
    return teacher, classroom, learners


def test_unknown_teacher_gets_end_message(db_session):
    response = handle_ussd(db_session, "+254700999999", "")
    assert response.startswith("END Namba hii haijasajiliwa")
    assert "This number is not registered" in response


def test_attendance_confirmation_saves_and_resubmission_overwrites(db_session):
    _, classroom, learners = build_teacher(db_session)
    phone = "+254700123456"
    assert handle_ussd(db_session, phone, "1").startswith("CON Select class")
    assert "absent roll" in handle_ussd(db_session, phone, f"1*{classroom.id}").lower()
    assert "Learner 2" in handle_ussd(db_session, phone, f"1*{classroom.id}*02")
    response = handle_ussd(db_session, phone, f"1*{classroom.id}*02*1")
    assert response.startswith("END Saved attendance")
    today_records = {record.learner_id: record.present for record in db_session.query(AttendanceRecord)}
    assert today_records == {learners[0].id: True, learners[1].id: False, learners[2].id: True}
    handle_ussd(db_session, phone, f"1*{classroom.id}*0*1")
    today_records = {record.learner_id: record.present for record in db_session.query(AttendanceRecord)}
    assert all(today_records.values())


def test_roll_validation_and_cancel_do_not_write(db_session):
    _, classroom, _ = build_teacher(db_session)
    phone = "+254700123456"
    assert "Unknown roll" in handle_ussd(db_session, phone, f"1*{classroom.id}*99")
    assert handle_ussd(db_session, phone, f"1*{classroom.id}*01*0").startswith("END Attendance cancelled")
    assert db_session.query(AttendanceRecord).count() == 0


def test_blank_absent_list_prompts_again(db_session):
    _, classroom, _ = build_teacher(db_session)

    response = handle_ussd(db_session, "+254700123456", f"1*{classroom.id}*")

    assert response.startswith("CON Enter absent roll numbers")
    assert db_session.query(AttendanceRecord).count() == 0


def _flag(db_session, learner, level="at_risk", score=62):
    from datetime import date

    from app.models import RiskSnapshot

    db_session.add(
        RiskSnapshot(
            learner_id=learner.id,
            date=date.today(),
            score=score,
            level=level,
            reasons=["3 consecutive school-day absences (+30)", "Parent reported fees issue (+15)"],
        )
    )
    db_session.flush()


def test_main_menu_greets_teacher_and_lists_options(db_session):
    build_teacher(db_session)
    response = handle_ussd(db_session, "0700123456", "")
    assert response.startswith("CON BakiShule - Teacher")
    for option in ["1. Mark attendance", "2. Class summary", "3. At-risk learners", "4. Log behaviour",
                   "5. Find learner", "6. Change language / Badilisha lugha"]:
        assert option in response


def test_at_risk_lists_only_flagged_and_shows_details(db_session):
    _, _, learners = build_teacher(db_session)
    _flag(db_session, learners[1])
    _flag(db_session, learners[2], level="green", score=5)
    listing = handle_ussd(db_session, "+254700123456", "3*1")
    assert "1. 02 Learner 2 AT RISK 62" in listing
    assert "Learner 3" not in listing
    detail = handle_ussd(db_session, "+254700123456", "3*1*1")
    assert detail.startswith("END 02 Learner 2 (5A)")
    assert "Risk: AT RISK 62/100" in detail


def test_learner_lookup_accepts_roll_without_leading_zero(db_session):
    build_teacher(db_session)
    assert handle_ussd(db_session, "+254700123456", "5*1").startswith("CON 5A: enter learner roll")
    assert handle_ussd(db_session, "+254700123456", "5*1*2").startswith("END 02 Learner 2 (5A)")
    assert "No learner with roll 9" in handle_ussd(db_session, "+254700123456", "5*1*9")


def test_double_zero_returns_to_main_menu(db_session):
    build_teacher(db_session)
    assert handle_ussd(db_session, "+254700123456", "1*1*00").startswith("CON BakiShule - Teacher")
    assert handle_ussd(db_session, "+254700123456", "1*1*00*2*1").startswith("END 5A")


def test_every_screen_fits_ussd_limit(db_session):
    _, _, learners = build_teacher(db_session)
    for learner in learners:
        _flag(db_session, learner, level="critical", score=90)
    for text in ["", "1", "1*1", "1*1*01 02 03", "2*1", "3*1", "3*1*1", "4*1", "4*1*1", "4*1*1*2", "5*1*1", "6"]:
        assert len(handle_ussd(db_session, "+254700123456", text)) <= 182, text


def test_attendance_save_defers_sms_when_runner_given(db_session):
    _, classroom, _ = build_teacher(db_session)
    deferred = []

    response = handle_ussd(
        db_session, "+254700123456", f"1*{classroom.id}*02*1", defer=lambda fn, *args: deferred.append((fn, args))
    )

    assert response.startswith("END Saved attendance")
    assert len(deferred) == 1
    assert deferred[0][0].__name__ == "run_escalations"
    assert len(deferred[0][1][0]) == 3  # one (learner, snapshot, previous_level) per learner
