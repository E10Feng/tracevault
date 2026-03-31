from __future__ import annotations
import os
from typing import Optional

from .models import TraceEntry


class Summarizer:
    def __init__(self, openai_client=None):
        if openai_client is not None:
            self._client = openai_client
        else:
            try:
                import openai
                api_key = os.environ.get("OPENAI_API_KEY")
                self._client = openai.OpenAI(api_key=api_key) if api_key else None
            except ImportError:
                self._client = None

    def summarize_step(self, entry: TraceEntry) -> str:
        """Summarize a single trace entry using GPT-4o-mini."""
        if self._client is None:
            return f"Step {entry.step_index}: {entry.entry_type}"

        prompt = (
            f"Given this agent step: {entry.entry_type} with payload {entry.payload}, "
            "write one sentence explaining what the agent decided and why."
        )
        response = self._client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
        )
        return response.choices[0].message.content.strip()

    def summarize_session(self, entries: list[TraceEntry]) -> str:
        """Summarize an entire session using GPT-4o-mini."""
        if self._client is None or not entries:
            return f"Session with {len(entries)} steps."

        steps_desc = "\n".join(
            f"Step {e.step_index} ({e.entry_type}): {e.payload}"
            for e in entries
        )
        prompt = (
            f"Summarize the following agent session in 2-3 sentences:\n{steps_desc}"
        )
        response = self._client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()
