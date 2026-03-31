from __future__ import annotations
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Optional

from langchain_core.callbacks import BaseCallbackHandler

from .chain import sign_entry
from .models import TraceEntry, TraceSession
from .storage import TraceStorage
from .summarizer import Summarizer


_executor = ThreadPoolExecutor(max_workers=2)


class TraceVaultCallbackHandler(BaseCallbackHandler):
    def __init__(
        self,
        session_id: str,
        agent_name: str,
        storage: TraceStorage,
        secret: str,
        summarizer: Optional[Summarizer] = None,
    ):
        super().__init__()
        self.session_id = session_id
        self.agent_name = agent_name
        self.storage = storage
        self.secret = secret
        self.summarizer = summarizer
        self._step_index = 0
        self._last_hash = "GENESIS"

    def _record_event(self, entry_type: str, payload: dict):
        entry_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        prev_hash = self._last_hash
        hmac_hash = sign_entry(entry_id, payload, prev_hash, self.secret)

        entry = TraceEntry(
            id=entry_id,
            session_id=self.session_id,
            step_index=self._step_index,
            entry_type=entry_type,
            payload=payload,
            summary=None,
            hmac_hash=hmac_hash,
            prev_hash=prev_hash,
            created_at=now,
        )
        self.storage.add_entry(entry)
        self._last_hash = hmac_hash
        self._step_index += 1

        # Fire async summarization best-effort
        if self.summarizer is not None:
            entry_copy = entry.model_copy()
            _executor.submit(self._async_summarize, entry_copy)

        return entry

    def _async_summarize(self, entry: TraceEntry):
        try:
            summary = self.summarizer.summarize_step(entry)
            self.storage.update_entry_summary(entry.id, summary)
        except Exception:
            pass

    def on_llm_start(self, serialized: dict, prompts: list[str], **kwargs):
        payload = {
            "serialized": serialized.get("name", str(serialized)) if serialized else {},
            "prompts": prompts,
        }
        self._record_event("llm_start", payload)

    def on_llm_end(self, response: Any, **kwargs):
        try:
            generations = []
            if hasattr(response, "generations"):
                for gen_list in response.generations:
                    for gen in gen_list:
                        if hasattr(gen, "text"):
                            generations.append(gen.text)
                        else:
                            generations.append(str(gen))
            payload = {"generations": generations}
        except Exception:
            payload = {"response": str(response)}
        self._record_event("llm_end", payload)

    def on_tool_start(self, serialized: dict, input_str: str, **kwargs):
        payload = {
            "tool": serialized.get("name", str(serialized)) if serialized else {},
            "input": input_str,
        }
        self._record_event("tool_start", payload)

    def on_tool_end(self, output: str, **kwargs):
        payload = {"output": str(output)}
        self._record_event("tool_end", payload)

    def on_chain_start(self, serialized: dict, inputs: dict, **kwargs):
        payload = {
            "chain": serialized.get("name", str(serialized)) if serialized else {},
            "inputs": {k: str(v) for k, v in inputs.items()} if inputs else {},
        }
        self._record_event("chain_start", payload)

    def on_chain_end(self, outputs: dict, **kwargs):
        payload = {
            "outputs": {k: str(v) for k, v in outputs.items()} if outputs else {},
        }
        self._record_event("chain_end", payload)


class trace_session:
    """Can be used as a decorator or context manager."""

    def __init__(
        self,
        session_id: str,
        agent_name: str = "agent",
        db_path: str = "tracevault.db",
        secret: Optional[str] = None,
        storage: Optional[TraceStorage] = None,
    ):
        self.session_id = session_id
        self.agent_name = agent_name
        self.db_path = db_path
        self.secret = secret or os.environ.get("TRACEVAULT_SECRET", "test-secret")
        self._storage = storage
        self._handler: Optional[TraceVaultCallbackHandler] = None

    def _get_storage(self) -> TraceStorage:
        if self._storage is not None:
            return self._storage
        return TraceStorage(self.db_path)

    def _setup(self) -> TraceVaultCallbackHandler:
        storage = self._get_storage()
        session = TraceSession(
            session_id=self.session_id,
            agent_name=self.agent_name,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata={},
        )
        storage.create_session(session)
        handler = TraceVaultCallbackHandler(
            session_id=self.session_id,
            agent_name=self.agent_name,
            storage=storage,
            secret=self.secret,
        )
        self._handler = handler
        return handler

    def __call__(self, func):
        """Decorator usage."""
        @wraps(func)
        def wrapper(*args, **kwargs):
            handler = self._setup()
            return func(*args, handler=handler, **kwargs)
        return wrapper

    def __enter__(self) -> TraceVaultCallbackHandler:
        """Context manager usage."""
        return self._setup()

    def __exit__(self, *args):
        pass
