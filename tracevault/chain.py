from __future__ import annotations
import hashlib
import hmac
import json
from typing import Optional

from .models import TraceEntry


def sign_entry(entry_id: str, payload: dict, prev_hash: str, secret: str) -> str:
    """Sign a trace entry using HMAC-SHA256."""
    msg = (entry_id + json.dumps(payload, sort_keys=True) + prev_hash).encode()
    return hmac.new(secret.encode(), msg=msg, digestmod=hashlib.sha256).hexdigest()


def verify_entry(entry: TraceEntry, secret: str) -> bool:
    """Verify a single entry's HMAC hash."""
    expected = sign_entry(entry.id, entry.payload, entry.prev_hash, secret)
    return hmac.compare_digest(expected, entry.hmac_hash)


def verify_chain(entries: list[TraceEntry], secret: str) -> tuple[bool, Optional[int]]:
    """
    Walk the full chain and verify all entries.
    Returns (valid, broken_at_step) where broken_at_step is the step_index of the first broken entry.
    """
    if not entries:
        return True, None

    prev_hash = "GENESIS"

    for entry in entries:
        # Verify prev_hash linkage
        if entry.prev_hash != prev_hash:
            return False, entry.step_index

        # Verify HMAC
        if not verify_entry(entry, secret):
            return False, entry.step_index

        prev_hash = entry.hmac_hash

    return True, None
