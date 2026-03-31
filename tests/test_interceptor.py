"""Tests for TraceVaultCallbackHandler."""
import uuid
from datetime import datetime, timezone

import pytest

from tracevault.chain import verify_entry
from tracevault.interceptor import TraceVaultCallbackHandler
from tracevault.models import TraceSession
from tracevault.storage import TraceStorage

SECRET = "test-secret"


def make_storage(tmp_path) -> TraceStorage:
    storage = TraceStorage(str(tmp_path / "test.db"))
    session = TraceSession(
        session_id="test-sess",
        agent_name="test-agent",
        created_at=datetime.now(timezone.utc).isoformat(),
        metadata={},
    )
    storage.create_session(session)
    return storage


def make_handler(tmp_path) -> TraceVaultCallbackHandler:
    storage = make_storage(tmp_path)
    return TraceVaultCallbackHandler(
        session_id="test-sess",
        agent_name="test-agent",
        storage=storage,
        secret=SECRET,
    )


def test_interceptor_captures_llm_events(tmp_path):
    """Fire on_llm_start + on_llm_end manually, verify 2 entries with valid HMACs."""
    handler = make_handler(tmp_path)
    storage = handler.storage

    handler.on_llm_start(
        serialized={"name": "TestLLM"},
        prompts=["Hello, world!"],
    )
    # Create a mock LLMResult-like object
    class MockGeneration:
        text = "I am an LLM response"

    class MockLLMResult:
        generations = [[MockGeneration()]]

    handler.on_llm_end(response=MockLLMResult())

    entries = storage.get_entries("test-sess")
    assert len(entries) == 2
    assert entries[0].entry_type == "llm_start"
    assert entries[1].entry_type == "llm_end"

    for entry in entries:
        assert verify_entry(entry, SECRET) is True


def test_interceptor_captures_tool_events(tmp_path):
    """Fire on_tool_start + on_tool_end, verify entry_types."""
    handler = make_handler(tmp_path)
    storage = handler.storage

    handler.on_tool_start(
        serialized={"name": "search_tool"},
        input_str="query string",
    )
    handler.on_tool_end(output="search results")

    entries = storage.get_entries("test-sess")
    assert len(entries) == 2
    assert entries[0].entry_type == "tool_start"
    assert entries[1].entry_type == "tool_end"

    for entry in entries:
        assert verify_entry(entry, SECRET) is True
