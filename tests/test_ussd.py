from app.models import AttendanceRecord, ClassRoom, Learner, School, Teacher
from app.routes.ussd import handle_ussd


def build_teacher(db_session):
    school = School(name="Test School", county="Nairobi")
    teacher = Teacher(name="Teacher", phone="+254700123456")
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
    assert handle_ussd(db_session, "+254700999999", "") == (
        "END Number not registered. Contact your school admin."
    )


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
