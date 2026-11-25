from datetime import date

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models import ClassRoom, Intervention, Learner, RiskSnapshot, School, Teacher


def create_flagged_learner(db_session):
    school = School(name="Test School", county="Nairobi")
    teacher = Teacher(name="Teacher", phone="+254700123456")
    head = Teacher(name="Head", phone="+254700123457", role="head_teacher")
    classroom = ClassRoom(name="5A", school=school, teacher=teacher)
    head_class = ClassRoom(name="6A", school=school, teacher=head)
    learner = Learner(
        name="Asha Njeri",
        roll_number="01",
        classroom=classroom,
        gender="female",
        guardian_name="Parent",
        guardian_phone="+254711123456",
        sponsor_consent=False,
    )
    db_session.add_all([school, teacher, head, classroom, head_class, learner])
    db_session.flush()
    db_session.add_all([
        RiskSnapshot(learner_id=learner.id, date=date.today(), score=80, level="critical", reasons=["Fee reply"]),
        Intervention(
            learner_id=learner.id,
            type="sponsor_flag",
            status="open",
            metadata_json={"reason": "parent_fees", "need": "Fees requested"},
        ),
    ])
    db_session.commit()
    return learner


def test_dashboard_and_at_risk_pages_render(db_session):
    create_flagged_learner(db_session)
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as client:
            assert client.get("/").status_code == 200
            response = client.get("/at-risk")
            assert response.status_code == 200
            assert "Asha Njeri" in response.text
            assert "Swipe horizontally to see parent replies and learner details." in response.text
            assert client.get("/learners/1").status_code == 200
            for path in ("/partials/summary", "/partials/at-risk", "/partials/sponsors"):
                assert client.get(path).status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_sponsor_view_anonymizes_and_payment_is_mockable(db_session, monkeypatch):
    learner = create_flagged_learner(db_session)
    calls = []
    monkeypatch.setattr(
        "app.routes.dashboard.payment_service.pay_sponsor_fee",
        lambda **kwargs: {"status": "mocked", "transaction_id": "DEMO-123"},
    )
    monkeypatch.setattr(
        "app.services.escalation.at_client.send_sms",
        lambda phone, text: calls.append((phone, text)) or {"status": "mocked"},
    )
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as client:
            response = client.get("/sponsors")
            assert "A. (anonymised)" in response.text
            assert "Asha Njeri" not in response.text
            result = client.post(f"/sponsors/{learner.id}/pay", follow_redirects=False)
            assert result.status_code == 303
    finally:
        app.dependency_overrides.clear()
    assert len(calls) == 3
    assert db_session.query(Intervention).filter_by(type="fee_payment").count() == 4
