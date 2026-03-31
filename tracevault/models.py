from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class TraceEntry(BaseModel):
    id: str
    session_id: str
    step_index: int
    entry_type: str
    payload: dict
    summary: Optional[str] = None
    hmac_hash: str
    prev_hash: str
    created_at: str


class TraceSession(BaseModel):
    session_id: str
    agent_name: str
    created_at: str
    metadata: dict = {}
