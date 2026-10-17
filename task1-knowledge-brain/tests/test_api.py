
from fastapi.testclient import TestClient

from app.api.server import app
from app.ingestion.parser import parse_article
from app.ingestion.storage import ArticleStore


client = TestClient(app)


def create_test_database(tmp_path):
    store = ArticleStore(tmp_path / "api_test.db")
    article = parse_article(
        """
        <html><body><main>
        <h1>Configure Payments</h1>
        <p>Open payment settings to configure payment options.</p>
        </main></body></html>
        """,
        "https://support.brilliantdirectories.com/support/payments",
    )
    store.save_article(article)
    return store.db_path, article


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ask_endpoint_returns_answer_and_source(tmp_path, monkeypatch):
    db_path, article = create_test_database(tmp_path)
    monkeypatch.setattr("app.api.routes.DEFAULT_DB_PATH", db_path)
    monkeypatch.setenv("KNOWLEDGE_BRAIN_MOCK_MODE", "true")

    response = client.post(
        "/ask",
        json={"question": "How do I configure payment settings?"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["abstained"] is False
    assert "[S1]" in data["answer"]
    assert data["sources"][0]["url"] == article.url


def test_ask_endpoint_abstains_without_relevant_evidence(
    tmp_path, monkeypatch
):
    db_path, _ = create_test_database(tmp_path)
    monkeypatch.setattr("app.api.routes.DEFAULT_DB_PATH", db_path)
    monkeypatch.setenv("KNOWLEDGE_BRAIN_MOCK_MODE", "true")

    response = client.post(
        "/ask",
        json={"question": "quantum spacecraft engine"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["abstained"] is True
    assert data["sources"] == []


def test_ask_endpoint_rejects_empty_question():
    response = client.post("/ask", json={"question": ""})

    assert response.status_code == 422


def test_create_and_list_escalations(tmp_path, monkeypatch):
    db_path = tmp_path / "escalation_api.db"
    monkeypatch.setattr("app.api.routes.DEFAULT_DB_PATH", db_path)

    created = client.post(
        "/escalations",
        json={
            "question": "How do I configure a payment gateway?",
            "reason": "The available evidence was insufficient.",
        },
    )

    assert created.status_code == 201
    item = created.json()
    assert item["status"] == "pending"

    listed = client.get("/escalations?status=pending")

    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == item["id"]


def test_resolve_escalation_endpoint(tmp_path, monkeypatch):
    db_path = tmp_path / "escalation_update_api.db"
    monkeypatch.setattr("app.api.routes.DEFAULT_DB_PATH", db_path)

    created = client.post(
        "/escalations",
        json={
            "question": "Test question",
            "reason": "Needs human review",
        },
    )
    escalation_id = created.json()["id"]

    updated = client.patch(
        f"/escalations/{escalation_id}",
        json={
            "status": "resolved",
            "resolution": "Provided the correct documentation.",
        },
    )

    assert updated.status_code == 200
    assert updated.json()["status"] == "resolved"


def test_resolving_without_note_is_rejected(tmp_path, monkeypatch):
    db_path = tmp_path / "escalation_invalid_api.db"
    monkeypatch.setattr("app.api.routes.DEFAULT_DB_PATH", db_path)

    created = client.post(
        "/escalations",
        json={
            "question": "Test question",
            "reason": "Needs human review",
        },
    )
    escalation_id = created.json()["id"]

    response = client.patch(
        f"/escalations/{escalation_id}",
        json={"status": "resolved"},
    )

    assert response.status_code == 422
def test_ask_abstention_creates_escalation(tmp_path, monkeypatch):
    from app.escalation import EscalationQueue
    from app.ingestion.storage import ArticleStore

    db_path = tmp_path / "auto_escalation.db"

    # Initialize an empty test database.
    ArticleStore(db_path)

    monkeypatch.setattr(
        "app.api.routes.DEFAULT_DB_PATH",
        db_path,
    )
    monkeypatch.setenv("KNOWLEDGE_BRAIN_MOCK_MODE", "true")

    response = client.post(
        "/ask",
        json={"question": "quantum spacecraft engine"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["abstained"] is True
    assert data["sources"] == []
    assert data["escalation_id"] is not None

    queue = EscalationQueue(db_path)
    item = queue.get(data["escalation_id"])

    assert item is not None
    assert item["question"] == "quantum spacecraft engine"
    assert item["status"] == "pending"
