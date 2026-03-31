"""Tests for HMAC chain functions."""
import uuid
from datetime import datetime, timezone

from tracevault.chain import sign_entry, verify_entry, verify_chain
from tracevault.models import TraceEntry

SECRET = "test-secret"


def make_entry(step_index: int, prev_hash: str, payload: dict = None) -> TraceEntry:
    entry_id = str(uuid.uuid4())
    if payload is None:
        payload = {"step": step_index, "data": f"value_{step_index}"}
    hmac_hash = sign_entry(entry_id, payload, prev_hash, SECRET)
    return TraceEntry(
        id=entry_id,
        session_id="test-session",
        step_index=step_index,
        entry_type="test",
        payload=payload,
        summary=None,
        hmac_hash=hmac_hash,
        prev_hash=prev_hash,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def test_hmac_chain_genesis():
    """Create first entry with prev_hash='GENESIS', verify returns True."""
    entry = make_entry(0, "GENESIS")
    assert verify_entry(entry, SECRET) is True


def test_hmac_chain_multi_entry():
    """Create 5 chained entries, verify_chain returns True, broken_at is None."""
    entries = []
    prev_hash = "GENESIS"
    for i in range(5):
        entry = make_entry(i, prev_hash)
        entries.append(entry)
        prev_hash = entry.hmac_hash

    valid, broken_at = verify_chain(entries, SECRET)
    assert valid is True
    assert broken_at is None


def test_hmac_chain_tamper_detection():
    """Create 5 entries, mutate payload of entry at step_index=2, verify_chain returns False."""
    entries = []
    prev_hash = "GENESIS"
    for i in range(5):
        entry = make_entry(i, prev_hash)
        entries.append(entry)
        prev_hash = entry.hmac_hash

    # Tamper with the entry at step_index=2 by creating a modified copy
    tampered = entries[2].model_copy(update={"payload": {"tampered": True}})
    entries[2] = tampered

    valid, broken_at = verify_chain(entries, SECRET)
    assert valid is False
    assert broken_at == 2
