"""Demo agent using TraceVault to trace LangChain agent interactions."""
from __future__ import annotations
import os
import uuid

from dotenv import load_dotenv

load_dotenv()

from tracevault import TraceStorage, TraceVaultCallbackHandler, TraceSession
from tracevault.chain import verify_chain


def run_demo():
    session_id = str(uuid.uuid4())
    secret = os.environ.get("TRACEVAULT_SECRET", "demo-secret")

    storage = TraceStorage("demo.db")
    session = TraceSession(
        session_id=session_id,
        agent_name="demo-agent",
        created_at="2024-01-01T00:00:00+00:00",
        metadata={"demo": True},
    )
    storage.create_session(session)

    handler = TraceVaultCallbackHandler(
        session_id=session_id,
        agent_name="demo-agent",
        storage=storage,
        secret=secret,
    )

    # Simulate LangChain callbacks
    handler.on_chain_start(
        serialized={"name": "DemoChain"},
        inputs={"input": "What is the capital of France?"},
    )

    handler.on_llm_start(
        serialized={"name": "gpt-4o-mini"},
        prompts=["What is the capital of France?"],
    )

    class MockGen:
        text = "The capital of France is Paris."

    class MockResult:
        generations = [[MockGen()]]

    handler.on_llm_end(response=MockResult())

    handler.on_chain_end(outputs={"output": "The capital of France is Paris."})

    # Verify the chain
    entries = storage.get_entries(session_id)
    valid, broken_at = verify_chain(entries, secret)

    print(f"Session ID: {session_id}")
    print(f"Entries recorded: {len(entries)}")
    print(f"Chain valid: {valid}")
    for entry in entries:
        print(f"  Step {entry.step_index}: {entry.entry_type} | HMAC: {entry.hmac_hash[:16]}...")


if __name__ == "__main__":
    run_demo()
