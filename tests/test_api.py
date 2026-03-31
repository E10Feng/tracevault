"""Tests for the FastAPI server."""
import json
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from tracevault.chain import sign_entry
from tracevault.models import TraceEntry, TraceSession
from tracevault.server.app import app, get_storage, get_secret
from tracevault.storage import TraceStorage

SECRET = "test-secret"


def make_in_memory_storage() -> TraceStorage:
    return TraceStorage(":memory:")


def make_session(session_id: str = None, agent_name: str = "test-agent") -> TraceSession:
    return TraceSession(
        session_id=session_id or str(uuid.uuid4()),
        agent_name=agent_name,
        created_at=datetime.now(timezone.utc).isoformat(),
        metadata={},
    )


def make_entry(session_id: str, step_index: int, prev_hash: str) -> TraceEntry:
    entry_id = str(uuid.uuid4())
    payload = {"step": step_index, "data": f"val_{step_index}"}
    hmac_hash = sign_entry(entry_id, payload, prev_hash, SECRET)
    return TraceEntry(
        id=entry_id,
        session_id=session_id,
        step_index=step_index,
        entry_type="test_event",
        payload=payload,
        summary=None,
        hmac_hash=hmac_hash,
        prev_hash=prev_hash,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def seed_session_with_entries(storage: TraceStorage, session_id: str, n_entries: int):
    session = make_session(session_id)
    storage.create_session(session)
    prev_hash = "GENESIS"
    entries = []
    for i in range(n_entries):
        entry = make_entry(session_id, i, prev_hash)
        storage.add_entry(entry)
        entries.append(entry)
        prev_hash = entry.hmac_hash
    return session, entries


@pytest.fixture
def client_with_storage():
    storage = make_in_memory_storage()

    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_secret] = lambda: SECRET

    client = TestClient(app)
    yield client, storage

    app.dependency_overrides.clear()


def test_api_list_sessions(client_with_storage):
    """Seed 2 sessions, GET /sessions, verify 200 with 2 items."""
    client, storage = client_with_storage

    seed_session_with_entries(storage, "sess-001", 2)
    seed_session_with_entries(storage, "sess-002", 3)

    response = client.get("/sessions")
    assert response.status_code == 200
    data = response.json()
    assert "sessions" in data
    assert len(data["sessions"]) == 2


def test_api_get_session_with_chain_valid(client_with_storage):
    """Seed session + 3 chained entries, GET /sessions/{id}, verify chain_valid=true."""
    client, storage = client_with_storage

    seed_session_with_entries(storage, "sess-valid", 3)

    response = client.get("/sessions/sess-valid")
    assert response.status_code == 200
    data = response.json()
    assert data["chain_valid"] is True
    assert len(data["entries"]) == 3


def test_api_verify_tampered_session(client_with_storage):
    """Seed session + 4 entries, mutate entry 2 payload, verify chain_valid=false."""
    client, storage = client_with_storage

    _, entries = seed_session_with_entries(storage, "sess-tampered", 4)

    # Mutate the payload of the entry at step_index=2
    storage.mutate_entry_payload_for_testing(entries[2].id, {"tampered": True})

    response = client.get("/sessions/sess-tampered/verify")
    assert response.status_code == 200
    data = response.json()
    assert data["chain_valid"] is False
    assert data["broken_at_step"] == 2


def test_api_export_json(client_with_storage):
    """Seed session, GET /export/{id}.json, verify valid JSON with session_id and entries."""
    client, storage = client_with_storage

    seed_session_with_entries(storage, "sess-export", 2)

    response = client.get("/export/sess-export.json")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "sess-export"
    assert "entries" in data


def test_api_export_csv(client_with_storage):
    """Seed session + 3 entries, GET /export/{id}.csv, verify CSV with header + 3 rows."""
    client, storage = client_with_storage

    seed_session_with_entries(storage, "sess-csv", 3)

    response = client.get("/export/sess-csv.csv")
    assert response.status_code == 200
    lines = response.text.strip().split("\n")
    # 1 header + 3 data rows
    assert len(lines) == 4
    header = lines[0]
    assert "session_id" in header
    assert "entry_id" in header


def test_api_session_not_found(client_with_storage):
    """GET /sessions/does-not-exist, verify 404."""
    client, storage = client_with_storage

    response = client.get("/sessions/does-not-exist")
    assert response.status_code == 404
