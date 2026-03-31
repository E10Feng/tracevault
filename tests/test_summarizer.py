"""Tests for Summarizer."""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from tracevault.models import TraceEntry
from tracevault.summarizer import Summarizer


def make_entry() -> TraceEntry:
    entry_id = str(uuid.uuid4())
    return TraceEntry(
        id=entry_id,
        session_id="test-session",
        step_index=0,
        entry_type="llm_start",
        payload={"prompts": ["What is the weather?"]},
        summary=None,
        hmac_hash="fakehash",
        prev_hash="GENESIS",
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def test_summarizer_mock():
    """Mock openai client, verify summarize_step returns non-empty string."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "The agent decided to query the weather API to get current conditions."
    mock_client.chat.completions.create.return_value = mock_response

    summarizer = Summarizer(openai_client=mock_client)
    entry = make_entry()
    result = summarizer.summarize_step(entry)

    assert isinstance(result, str)
    assert len(result) > 0
    # Verify no real API calls were made
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args
    assert call_kwargs.kwargs["model"] == "gpt-4o-mini"
