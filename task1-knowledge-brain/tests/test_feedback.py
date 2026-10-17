
import pytest

from app.feedback import FeedbackStore


def test_submit_and_retrieve_feedback(tmp_path):
    store = FeedbackStore(tmp_path / "feedback.db")

    item = store.submit(
        question="How do I configure SEO?",
        answer="Open the SEO settings.",
        rating="positive",
        comment="Helpful answer",
    )

    assert item["id"] is not None
    assert item["rating"] == "positive"
    assert item["comment"] == "Helpful answer"

    retrieved = store.get(item["id"])
    assert retrieved["question"] == "How do I configure SEO?"


def test_list_feedback_by_rating(tmp_path):
    store = FeedbackStore(tmp_path / "feedback.db")

    store.submit("Question 1", "Answer 1", "positive")
    store.submit("Question 2", "Answer 2", "negative")

    items = store.list_items(rating="negative")

    assert len(items) == 1
    assert items[0]["question"] == "Question 2"


def test_invalid_rating_is_rejected(tmp_path):
    store = FeedbackStore(tmp_path / "feedback.db")

    with pytest.raises(ValueError):
        store.submit("Question", "Answer", "neutral")


def test_empty_question_is_rejected(tmp_path):
    store = FeedbackStore(tmp_path / "feedback.db")

    with pytest.raises(ValueError):
        store.submit("  ", "Answer", "positive")
