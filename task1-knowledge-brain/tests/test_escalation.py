
from app.escalation import EscalationQueue


def test_create_and_list_escalation(tmp_path):
    queue = EscalationQueue(tmp_path / "test.db")

    item = queue.create(
        question="How do I configure a payment gateway?",
        reason="The available sources were insufficient.",
    )

    assert item["id"] is not None
    assert item["status"] == "pending"

    pending = queue.list_items(status="pending")

    assert len(pending) == 1
    assert pending[0]["question"] == (
        "How do I configure a payment gateway?"
    )


def test_resolve_escalation(tmp_path):
    queue = EscalationQueue(tmp_path / "test.db")

    item = queue.create("Test question", "Needs human review")

    updated = queue.update_status(
        item["id"],
        "resolved",
        resolution="Provided the correct documentation.",
    )

    assert updated["status"] == "resolved"
    assert updated["resolution"] == (
        "Provided the correct documentation."
    )


def test_invalid_resolution_is_rejected(tmp_path):
    queue = EscalationQueue(tmp_path / "test.db")

    item = queue.create("Test question", "Needs human review")

    try:
        queue.update_status(item["id"], "resolved")
    except ValueError as exc:
        assert "resolution note is required" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_missing_escalation_returns_none(tmp_path):
    queue = EscalationQueue(tmp_path / "test.db")

    assert queue.get(999) is None
