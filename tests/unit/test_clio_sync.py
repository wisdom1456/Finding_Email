"""Unit tests for Clio sync functionality."""

from src.legal_portal.api.routes.clio import categorize_clio_sync_items


def test_categorize_sync_items_all_new():
    """Test categorization when all items are new."""
    documents = [
        {"id": 1, "name": "Doc1.pdf", "created_at": "2026-01-01T00:00:00Z"},
        {"id": 2, "name": "Doc2.pdf", "created_at": "2026-01-02T00:00:00Z"},
    ]
    existing_docs = []

    new, updated = categorize_clio_sync_items(documents, [], [], existing_docs)

    assert len(new) == 2
    assert len(updated) == 0
    assert new[0]["type"] == "document"


def test_categorize_sync_items_all_updated():
    """Test categorization when all items are updates."""
    documents = [
        {"id": 1, "name": "Doc1.pdf", "created_at": "2026-01-01T00:00:00Z"},
    ]
    existing_docs = [
        {"metadata": {"clio_source": True, "clio_id": "1"}},
    ]

    new, updated = categorize_clio_sync_items(documents, [], [], existing_docs)

    assert len(new) == 0
    assert len(updated) == 1
    assert updated[0]["name"] == "Doc1.pdf"


def test_categorize_sync_items_mixed():
    """Test categorization with mix of new and updated items."""
    documents = [{"id": 1, "name": "Doc1.pdf", "created_at": None}]
    communications = [
        {"id": 2, "subject": "Email 1", "date": None},
        {"id": 3, "subject": "Email 2", "date": None},
    ]
    existing_docs = [
        {"metadata": {"clio_source": True, "clio_id": "1"}},
        {"metadata": {"clio_source": True, "clio_id": "2"}},
    ]

    new, updated = categorize_clio_sync_items(documents, communications, [], existing_docs)

    assert len(new) == 1  # Communication 3
    assert len(updated) == 2  # Document 1, Communication 2
    assert new[0]["type"] == "communication"
