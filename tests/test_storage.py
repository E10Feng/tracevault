"""Tests for TraceStorage."""
import uuid
from datetime import datetime, timezone

import pytest

from tracevault.chain import sign_entry
from tracevault.models import TraceEntry, TraceSession
from tracevault.storage import TraceStorage

SECRET = "test-secret"


def make_storage(tmp_path) -> TraceStorage:
    return TraceStorage(str(tmp_path / "test.db"))


def make_session(session_id: str = None) -> TraceSession:
    return TraceSession(
        session_id=session_id or str(uuid.uuid4()),
        agent_name="test-agent",
        created_at=datetime.now(timezone.utc).isoformat(),
        metadata={"env": "test"},
    )


def make_entry(session_id: str, step_index: int, prev_hash: str) -> TraceEntry:
    entry_id = str(uuid.uuid4())
    payload = {"step": step_index, "msg": f"message_{step_index}"}
    hmac_hash = sign_entry(entry_id, payload, prev_hash, SECRET)
    return TraceEntry(
        id=entry_id,
        session_id=session_id,
        step_index=step_index,
        entry_type="test_event",
        payload=payload,
        summary=f"Summary for step {step_index}",
        hmac_hash=hmac_hash,
        prev_hash=prev_hash,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def test_storage_write_and_read(tmp_path):
    """Write session + 3 entries, read back, verify all fields match."""
    storage = make_storage(tmp_path)
    session = make_session("sess-abc")
    storage.create_session(session)

    entries = []
    prev_hash = "GENESIS"
    for i in range(3):
        entry = make_entry(session.session_id, i, prev_hash)
        storage.add_entry(entry)
        entries.append(entry)
        prev_hash = entry.hmac_hash

    # Read back session
    read_session = storage.get_session("sess-abc")
    assert read_session is not None
    assert read_session.session_id == session.session_id
    assert read_session.agent_name == session.agent_name
    assert read_session.metadata == session.metadata

    # Read back entries
    read_entries = storage.get_entries("sess-abc")
    assert len(read_entries) == 3
    for orig, read in zip(entries, read_entries):
        assert orig.id == read.id
        assert orig.session_id == read.session_id
        assert orig.step_index == read.step_index
        assert orig.entry_type == read.entry_type
        assert orig.payload == read.payload
        assert orig.hmac_hash == read.hmac_hash
        assert orig.prev_hash == read.prev_hash
        assert orig.summary == read.summary


def test_storage_session_not_found(tmp_path):
    """get_session('nonexistent') returns None."""
    storage = make_storage(tmp_path)
    result = storage.get_session("nonexistent")
    assert result is None
