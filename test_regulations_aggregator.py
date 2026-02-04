import json
import sqlite3
import os
import pytest
from unittest.mock import patch, MagicMock

import regulations_aggregator as ra


@pytest.fixture(autouse=True)
def use_temp_db(tmp_path, monkeypatch):
    """Point DB_FILE at a temporary database for every test."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(ra, "DB_FILE", db_path)
    ra.init_db()
    yield db_path


# -- init_db -----------------------------------------------------------------

def test_init_db_creates_table(use_temp_db):
    conn = sqlite3.connect(use_temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='regulations'")
    assert cursor.fetchone() is not None
    conn.close()


def test_init_db_is_idempotent(use_temp_db):
    ra.init_db()  # second call should not error
    conn = sqlite3.connect(use_temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='regulations'")
    assert cursor.fetchone()[0] == 1
    conn.close()


# -- store_records -----------------------------------------------------------

def _make_record(id="doc-1", title="Test", source_last_modified="2026-01-01"):
    return {
        "id": id,
        "title": title,
        "description": "desc",
        "published_date": "2026-01-01",
        "full_text": "text",
        "source_last_modified": source_last_modified,
    }


def _count_rows(db_path):
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT count(*) FROM regulations").fetchone()[0]
    conn.close()
    return count


def _get_row(db_path, doc_id):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM regulations WHERE id = ?", (doc_id,)).fetchone()
    conn.close()
    return row


def test_store_records_inserts(use_temp_db):
    ra.store_records("federal", [_make_record()], "https://example.com")
    assert _count_rows(use_temp_db) == 1
    row = _get_row(use_temp_db, "doc-1")
    assert row["title"] == "Test"
    assert row["level"] == "federal"


def test_store_records_skips_missing_id(use_temp_db):
    ra.store_records("federal", [{"title": "no id"}], "https://example.com")
    assert _count_rows(use_temp_db) == 0


def test_store_records_skips_unchanged(use_temp_db):
    ra.store_records("federal", [_make_record(source_last_modified="2026-01-01")], "https://example.com")
    assert _count_rows(use_temp_db) == 1
    # Same source_last_modified — should skip
    ra.store_records("federal", [_make_record(source_last_modified="2026-01-01")], "https://example.com")
    assert _count_rows(use_temp_db) == 1


def test_store_records_updates_when_source_changed(use_temp_db):
    ra.store_records("federal", [_make_record(source_last_modified="2026-01-01")], "https://example.com")
    ra.store_records("federal", [_make_record(title="Updated", source_last_modified="2026-01-02")], "https://example.com")
    row = _get_row(use_temp_db, "doc-1")
    assert row["title"] == "Updated"
    assert row["source_last_modified"] == "2026-01-02"


def test_store_records_multiple(use_temp_db):
    records = [_make_record(id="a"), _make_record(id="b"), _make_record(id="c")]
    ra.store_records("local", records, "https://example.com")
    assert _count_rows(use_temp_db) == 3


# -- normalize_federal -------------------------------------------------------

def test_normalize_federal_extracts_attributes():
    data = [{
        "id": "FDA-2026-N-0001",
        "attributes": {
            "documentId": "FDA-2026-N-0001-0001",
            "title": "Federal Rule",
            "summary": "A summary",
            "postedDate": "2026-01-15",
            "lastModifiedDate": "2026-01-16",
        }
    }]
    records = ra.normalize_federal(data)
    assert len(records) == 1
    assert records[0]["id"] == "FDA-2026-N-0001-0001"
    assert records[0]["title"] == "Federal Rule"
    assert records[0]["description"] == "A summary"
    assert records[0]["published_date"] == "2026-01-15"
    assert records[0]["source_last_modified"] == "2026-01-16"


def test_normalize_federal_falls_back_to_item_id():
    data = [{"id": "FALLBACK-ID", "attributes": {"title": "No documentId"}}]
    records = ra.normalize_federal(data)
    assert records[0]["id"] == "FALLBACK-ID"


def test_normalize_federal_uses_abstract_if_no_summary():
    data = [{"id": "1", "attributes": {"abstract": "An abstract"}}]
    records = ra.normalize_federal(data)
    assert records[0]["description"] == "An abstract"


def test_normalize_federal_empty_input():
    assert ra.normalize_federal([]) == []


# -- normalize_state ---------------------------------------------------------

def test_normalize_state_extracts_fields():
    items = [{
        "id": {"lawId": "ABC", "activeDate": "2026-01-10"},
        "contentType": "LAW",
        "sourceId": "20260110.UPDATE",
        "sourceDateTime": "2026-01-10T00:00:00",
    }]
    records = ra.normalize_state(items)
    assert len(records) == 1
    assert records[0]["id"] == "nys-ABC-2026-01-10"
    assert records[0]["title"] == "LAW ABC"
    assert records[0]["description"] == "20260110.UPDATE"
    assert records[0]["source_last_modified"] == "2026-01-10T00:00:00"


def test_normalize_state_falls_back_to_string_id():
    items = [{"id": "FALLBACK"}]
    records = ra.normalize_state(items)
    assert "FALLBACK" in records[0]["id"]


def test_normalize_state_empty_input():
    assert ra.normalize_state([]) == []


# -- fetch functions (mocked HTTP) -------------------------------------------

def _mock_response(json_data, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status.return_value = None
    return mock


@patch("regulations_aggregator.requests.get")
def test_fetch_federal_stores_records(mock_get, use_temp_db, monkeypatch):
    monkeypatch.setattr(ra, "FEDERAL_API_KEY", "test-key")
    mock_get.return_value = _mock_response({
        "data": [{
            "id": "FED-001",
            "attributes": {
                "documentId": "FED-001-0001",
                "title": "Test Federal Doc",
                "summary": "Summary",
                "postedDate": "2026-01-20",
            }
        }]
    })
    ra.fetch_federal_updates()
    assert _count_rows(use_temp_db) == 1
    assert _get_row(use_temp_db, "FED-001-0001")["title"] == "Test Federal Doc"


@patch("regulations_aggregator.requests.get")
def test_fetch_federal_skips_without_key(mock_get, use_temp_db, monkeypatch):
    monkeypatch.setattr(ra, "FEDERAL_API_KEY", "")
    ra.fetch_federal_updates()
    mock_get.assert_not_called()


@patch("regulations_aggregator.requests.get")
def test_fetch_federal_handles_error(mock_get, use_temp_db, monkeypatch):
    monkeypatch.setattr(ra, "FEDERAL_API_KEY", "test-key")
    mock_get.side_effect = ra.requests.RequestException("timeout")
    ra.fetch_federal_updates()  # should not raise
    assert _count_rows(use_temp_db) == 0


@patch("regulations_aggregator.requests.get")
def test_fetch_state_stores_records(mock_get, use_temp_db, monkeypatch):
    monkeypatch.setattr(ra, "STATE_API_KEY", "test-key")
    mock_get.return_value = _mock_response({
        "result": {
            "items": [{
                "id": {"lawId": "AGM", "activeDate": "2026-01-10"},
                "contentType": "LAW",
                "sourceId": "food safety update",
                "sourceDateTime": "2026-01-10T00:00:00",
            }]
        }
    })
    ra.fetch_state_updates()
    assert _count_rows(use_temp_db) == 1


@patch("regulations_aggregator.requests.get")
def test_fetch_state_skips_without_key(mock_get, use_temp_db, monkeypatch):
    monkeypatch.setattr(ra, "STATE_API_KEY", "")
    ra.fetch_state_updates()
    mock_get.assert_not_called()


