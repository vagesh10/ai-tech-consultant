import os
import tempfile
from pathlib import Path

# Set the test database before importing the FastAPI application.
_temp_dir = tempfile.TemporaryDirectory()
os.environ["SOW_DB_PATH"] = str(Path(_temp_dir.name) / "test_sows.db")

from fastapi.testclient import TestClient
from app.main import app, startup

# Initialize the isolated test database before running requests.
startup()
client = TestClient(app)

TRANSCRIPT = """
Client: We need a customer portal with login and invoice downloads.
Consultant: We will develop the portal and integrate the billing API.
Client: We assume the billing API documentation will be available.
Consultant: Mobile app development is out of scope.
Client: Do we need multi-language support? We need to confirm this.
"""


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["database"] == "connected"


def test_analyze_transcript():
    response = client.post("/analyze", json={"transcript": TRANSCRIPT})

    assert response.status_code == 200
    result = response.json()

    assert result["review_required"] is True
    assert len(result["scope"]) == 1
    assert len(result["deliverables"]) == 1
    assert len(result["assumptions"]) == 1
    assert len(result["exclusions"]) == 1
    assert len(result["open_questions"]) == 1


def test_analyze_rejects_empty_transcript():
    response = client.post("/analyze", json={"transcript": "   "})

    assert response.status_code == 422


def test_generate_and_retrieve_sow():
    created = client.post(
        "/sow/generate",
        json={"transcript": TRANSCRIPT},
    )

    assert created.status_code == 200
    sow = created.json()
    sow_id = sow["id"]

    assert sow["status"] == "pending_review"
    assert sow["review_required"] is True

    retrieved = client.get(f"/sow/{sow_id}")

    assert retrieved.status_code == 200
    assert retrieved.json()["id"] == sow_id
    assert retrieved.json()["source_transcript"] == TRANSCRIPT


def test_sow_persists_after_app_restart():
    created = client.post(
        "/sow/generate",
        json={"transcript": TRANSCRIPT},
    )
    sow_id = created.json()["id"]

    # Simulate a new application startup using the same test database.
    from app.main import startup
    startup()

    retrieved = client.get(f"/sow/{sow_id}")

    assert retrieved.status_code == 200
    assert retrieved.json()["status"] == "pending_review"


def test_approval_is_persisted_and_cannot_be_repeated():
    created = client.post(
        "/sow/generate",
        json={"transcript": TRANSCRIPT},
    )
    sow_id = created.json()["id"]

    approval = client.post(
        f"/sow/{sow_id}/approve",
        json={"reviewer": "Project Manager"},
    )

    assert approval.status_code == 200
    assert approval.json()["sow"]["status"] == "approved"
    assert approval.json()["sow"]["approved_by"] == "Project Manager"
    assert approval.json()["sow"]["review_required"] is False

    repeated = client.post(
        f"/sow/{sow_id}/approve",
        json={"reviewer": "Project Manager"},
    )

    assert repeated.status_code == 409

    retrieved = client.get(f"/sow/{sow_id}")
    assert retrieved.json()["status"] == "approved"


def test_unknown_sow_returns_404():
    response = client.get("/sow/does-not-exist")

    assert response.status_code == 404


def test_approval_of_unknown_sow_returns_404():
    response = client.post(
        "/sow/does-not-exist/approve",
        json={"reviewer": "Project Manager"},
    )

    assert response.status_code == 404


import app.main as main_module


MOCK_FEASIBILITY = {
    "status": "unknown",
    "answer": "Mock response for testing.",
    "sources": [],
    "abstained": True,
    "mock_response": True,
    "note": "Test-only mock.",
}


def test_follow_up_updates_sow_and_reports_scope_changes(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "check_product_feasibility",
        lambda request_text: MOCK_FEASIBILITY,
    )

    created = client.post(
        "/sow/generate",
        json={"transcript": TRANSCRIPT},
    )

    assert created.status_code == 200
    sow_id = created.json()["id"]

    follow_up_transcript = """
    Client: We need a customer portal with login, invoice downloads,
    and report exports.
    Consultant: We will develop the portal and integrate the billing API.
    Client: We assume the billing API documentation will be available.
    Consultant: Mobile app development is out of scope.
    Client: We need to confirm multi-language support.
    """

    response = client.post(
        f"/sow/{sow_id}/follow-up",
        json={"transcript": follow_up_transcript},
    )

    assert response.status_code == 200

    result = response.json()

    assert result["sow"]["id"] == sow_id
    assert result["sow"]["status"] == "pending_review"
    assert result["sow"]["review_required"] is True
    assert result["sow"]["source_transcript"] == follow_up_transcript
    assert result["changes"]["scope_unchanged"] is False
    assert isinstance(result["changes"]["added_scope"], list)
    assert isinstance(result["changes"]["removed_scope"], list)
    assert result["product_feasibility"]["status"] == "unknown"
    assert result["review_required"] is True

    # Verify the updated SOW is persisted.
    retrieved = client.get(f"/sow/{sow_id}")

    assert retrieved.status_code == 200
    assert retrieved.json()["source_transcript"] == follow_up_transcript


def test_follow_up_unknown_sow_returns_404():
    response = client.post(
        "/sow/does-not-exist/follow-up",
        json={"transcript": "We need an additional reporting feature."},
    )

    assert response.status_code == 404


def test_follow_up_rejects_approved_sow(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "check_product_feasibility",
        lambda request_text: MOCK_FEASIBILITY,
    )

    created = client.post(
        "/sow/generate",
        json={"transcript": TRANSCRIPT},
    )

    assert created.status_code == 200
    sow_id = created.json()["id"]

    approval = client.post(
        f"/sow/{sow_id}/approve",
        json={"reviewer": "Project Manager"},
    )

    assert approval.status_code == 200

    response = client.post(
        f"/sow/{sow_id}/follow-up",
        json={"transcript": "We need an additional reporting feature."},
    )

    assert response.status_code == 409
