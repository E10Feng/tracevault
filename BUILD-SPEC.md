# TraceVault — Build Spec

## Overview

TraceVault is a Python library that wraps any LangGraph/LangChain agent and produces tamper-proof, natural-language audit trails. When an agent makes a consequential decision in production, TraceVault records every step — tool calls, LLM inputs/outputs, and an LLM-generated plain-English summary of why the agent did what it did.

**Who it's for:** Python teams deploying LLM agents in regulated industries (healthcare, finance, legal) who need agent decisions to be reconstructable, provable, and exportable for compliance review.

**Pain solved:** AI agents make opaque decisions in production with zero traceable record. When an agent leaks data, posts something wrong, or fabricates a billing explanation, teams cannot reconstruct the decision path. In regulated industries, no audit trail = no deployment approval.

---

## Architecture

```
Your Code
   |
   v
@trace_session(session_id, agent_fn)   ← TraceVault decorator/context manager
   |
   v
TraceVault Interceptor
   |
   +---> Captures: tool calls, LLM inputs, LLM outputs, timestamps
   |
   +---> HMAC-chains each entry (entry N signs entry N-1)
   |
   +---> LLM summarizer: "Why did the agent do this step?"
   |
   v
SQLite (tracevault.db)
   |
   v
FastAPI Server (localhost:8000)
   |
   +--- GET /sessions               → list sessions
   +--- GET /sessions/{id}          → full trace for session
   +--- GET /sessions/{id}/summary  → NL summary
   +--- GET /export/{id}.json       → export session
   +--- GET /export/{id}.csv        → export session as CSV
   |
   v
Minimal Web UI (Jinja2 + vanilla JS at /ui)
```

---

## Tech Stack

- **Python 3.10+**
- **FastAPI** + **Uvicorn** — API server
- **SQLite** (via `sqlite3` stdlib) — storage, zero-config for MVP
- **LangChain / LangGraph** — agent framework to intercept
- **`hmac` + `hashlib`** (stdlib) — HMAC-SHA256 chain signing
- **OpenAI SDK** (`openai>=1.0`) — LLM summarization of steps
- **Jinja2** — minimal web UI templates
- **pytest** — tests
- **python-dotenv** — env management
- **httpx** — test client for FastAPI

---

## File Structure

```
tracevault/
├── .gitignore
├── BUILD-SPEC.md
├── README.md
├── pyproject.toml          # or setup.py / requirements.txt
├── requirements.txt
├── .env.example
├── tracevault/
│   ├── __init__.py         # exports: trace_session, TraceVaultClient
│   ├── interceptor.py      # decorator + context manager that wraps agent calls
│   ├── chain.py            # HMAC chain logic (sign, verify)
│   ├── storage.py          # SQLite read/write for trace entries
│   ├── summarizer.py       # LLM call to generate NL step summaries
│   ├── models.py           # Pydantic models: TraceEntry, TraceSession
│   └── server/
│       ├── __init__.py
│       ├── app.py          # FastAPI app, routes
│       ├── templates/
│       │   ├── base.html
│       │   ├── sessions.html
│       │   └── session_detail.html
│       └── static/
│           └── style.css
├── tests/
│   ├── __init__.py
│   ├── test_chain.py       # HMAC chain integrity tests
│   ├── test_storage.py     # SQLite storage tests
│   ├── test_interceptor.py # Decorator wrapping + capture tests
│   ├── test_summarizer.py  # Summarizer (mocked LLM)
│   └── test_api.py         # FastAPI endpoint tests
└── examples/
    └── demo_agent.py       # A simple LangGraph agent wrapped with TraceVault
```

---

## Core Features (MVP scope only)

1. **Decorator/context manager interceptor** — `@trace_session(session_id)` wraps any Python callable (LangGraph agent, LangChain chain, or raw function). Automatically captures all LLM inputs/outputs and tool call events by monkey-patching the relevant LangChain callbacks.

2. **HMAC-chained log entries** — Every trace entry includes an HMAC-SHA256 signature over (entry_id + payload + previous_entry_hash). Chain breaks are detectable and reported as tampering. Secret key loaded from `TRACEVAULT_SECRET` env var.

3. **LLM step summarizer** — After each agent step completes, TraceVault calls the LLM with a structured prompt: "Given this agent step (tool calls + LLM output), write one sentence explaining what the agent decided and why." Stored alongside the raw trace entry. Summarizer is optional/async — raw trace is always saved first.

4. **FastAPI server + minimal UI** — `tracevault serve` starts a local server at `localhost:8000`. `/ui` renders a Jinja2-based read-only audit trail browser. Sessions are listed, clickable, and show step-by-step trace with NL summaries.

5. **JSON + CSV export** — `GET /export/{session_id}.json` and `.csv` return full trace data for compliance reporting. CSV flattens the trace (one row per step).

---

## Implementation Notes

- **Storage:** Use SQLite with two tables: `sessions` (session_id, created_at, agent_name, metadata JSON) and `trace_entries` (id, session_id, step_index, entry_type, payload JSON, summary, hmac_hash, prev_hash, created_at). No ORM — raw `sqlite3` for speed and zero deps.

- **HMAC chain:** The first entry in a session has `prev_hash = "GENESIS"`. Each subsequent entry signs `sha256(entry_id + json(payload) + prev_hash)` with `HMAC-SHA256(TRACEVAULT_SECRET)`. Verification walks the full chain and fails fast on any break.

- **Interceptor design:** Use LangChain's `BaseCallbackHandler` to hook into `on_llm_start`, `on_llm_end`, `on_tool_start`, `on_tool_end`, `on_chain_start`, `on_chain_end`. This gives us clean hooks without monkey-patching. For LangGraph, the callback is passed via `config={"callbacks": [tracer]}`.

- **Summarizer:** Default to `gpt-4o-mini` for cost efficiency. Summarization is best-effort — if it fails, log the error and continue. Never block the primary agent on summarization. Run async in background.

- **Environment:** `TRACEVAULT_SECRET` (required for HMAC), `OPENAI_API_KEY` (required for summarizer), `TRACEVAULT_DB` (optional, defaults to `tracevault.db`).

- **Thread safety:** SQLite writes are wrapped in a threading lock. Summarizer runs in a ThreadPoolExecutor (max 4 workers) to avoid blocking.

- **No external queue needed for MVP** — keep it simple, async summarization is fire-and-forget in threads.

---

## API / Interface

### REST Endpoints (FastAPI)

```
GET  /sessions
     → 200 { sessions: [{ session_id, agent_name, created_at, step_count }] }

GET  /sessions/{session_id}
     → 200 { session_id, agent_name, created_at, chain_valid: bool, entries: [...] }
     → 404 if not found

GET  /sessions/{session_id}/summary
     → 200 { session_id, summary: "Natural language overview of the session" }

GET  /export/{session_id}.json
     → 200 application/json — full trace JSON

GET  /export/{session_id}.csv
     → 200 text/csv — flattened trace CSV

GET  /sessions/{session_id}/verify
     → 200 { session_id, chain_valid: bool, broken_at_step: int | null }
```

### Python API

```python
from tracevault import trace_session

# As a decorator
@trace_session(session_id="session-123", agent_name="billing-agent")
def run_agent(query: str):
    # your LangGraph/LangChain agent code here
    ...

# As a context manager
with trace_session(session_id="session-456", agent_name="intake-agent") as tracer:
    result = my_agent.invoke({"input": query}, config={"callbacks": [tracer]})
```

### CLI

```
tracevault serve [--port 8000] [--db tracevault.db]
tracevault verify <session_id>
tracevault export <session_id> [--format json|csv]
```

---

## Setup & Run

```bash
# Install deps
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env: set TRACEVAULT_SECRET and OPENAI_API_KEY

# Run the API server
tracevault serve
# or: uvicorn tracevault.server.app:app --reload

# Run tests
pytest tests/ -v

# Run the demo agent
python examples/demo_agent.py
```

### requirements.txt contents:
```
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
langchain>=0.1.0
langgraph>=0.0.30
openai>=1.12.0
pydantic>=2.0.0
jinja2>=3.1.0
python-dotenv>=1.0.0
httpx>=0.26.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

---

## Test Cases

### 1. `test_hmac_chain_genesis`
**File:** `tests/test_chain.py`
**Run:** `pytest tests/test_chain.py::test_hmac_chain_genesis`
**What:** Create first entry with `prev_hash="GENESIS"`, verify signature validates correctly.
**Expected:** `chain.verify_entry(entry)` returns `True`.

### 2. `test_hmac_chain_multi_entry`
**File:** `tests/test_chain.py`
**Run:** `pytest tests/test_chain.py::test_hmac_chain_multi_entry`
**What:** Create 5 chained entries, verify the full chain passes.
**Expected:** `chain.verify_chain(entries)` returns `True`, `broken_at` is `None`.

### 3. `test_hmac_chain_tamper_detection`
**File:** `tests/test_chain.py`
**Run:** `pytest tests/test_chain.py::test_hmac_chain_tamper_detection`
**What:** Create 5 chained entries, mutate the payload of entry 3, re-run chain verification.
**Expected:** `chain.verify_chain(entries)` returns `False`, `broken_at` == 3.

### 4. `test_storage_write_and_read`
**File:** `tests/test_storage.py`
**Run:** `pytest tests/test_storage.py::test_storage_write_and_read`
**What:** Write a session and 3 entries to SQLite, read them back.
**Expected:** Returned entries match written entries exactly (all fields).

### 5. `test_storage_session_not_found`
**File:** `tests/test_storage.py`
**Run:** `pytest tests/test_storage.py::test_storage_session_not_found`
**What:** Query a session_id that does not exist.
**Expected:** `storage.get_session("nonexistent")` returns `None`.

### 6. `test_interceptor_captures_llm_events`
**File:** `tests/test_interceptor.py`
**Run:** `pytest tests/test_interceptor.py::test_interceptor_captures_llm_events`
**What:** Create a `TraceVaultCallbackHandler`, fire `on_llm_start` and `on_llm_end` events manually, verify entries were written to storage.
**Expected:** 2 entries in storage for the session (one start, one end). Both have valid HMAC.

### 7. `test_interceptor_captures_tool_events`
**File:** `tests/test_interceptor.py`
**Run:** `pytest tests/test_interceptor.py::test_interceptor_captures_tool_events`
**What:** Fire `on_tool_start` and `on_tool_end` events, verify captured.
**Expected:** 2 tool entries in storage. `entry_type` fields are `"tool_start"` and `"tool_end"`.

### 8. `test_summarizer_mock`
**File:** `tests/test_summarizer.py`
**Run:** `pytest tests/test_summarizer.py::test_summarizer_mock`
**What:** Mock `openai.chat.completions.create`, call `summarizer.summarize_step(entry)`, verify it returns a non-empty string without hitting real API.
**Expected:** Returns mock response string. No real API call made.

### 9. `test_api_list_sessions`
**File:** `tests/test_api.py`
**Run:** `pytest tests/test_api.py::test_api_list_sessions`
**What:** Seed DB with 2 sessions, call `GET /sessions`, verify response.
**Expected:** 200 response, `sessions` array has 2 items with correct `session_id` fields.

### 10. `test_api_get_session_with_chain_valid`
**File:** `tests/test_api.py`
**Run:** `pytest tests/test_api.py::test_api_get_session_with_chain_valid`
**What:** Seed DB with a session + 3 properly chained entries, call `GET /sessions/{id}`.
**Expected:** 200, `chain_valid: true`, `entries` has 3 items.

### 11. `test_api_verify_tampered_session`
**File:** `tests/test_api.py`
**Run:** `pytest tests/test_api.py::test_api_verify_tampered_session`
**What:** Seed DB with a session + 4 entries, directly mutate entry 2's payload in DB, call `GET /sessions/{id}/verify`.
**Expected:** 200, `chain_valid: false`, `broken_at_step: 2`.

### 12. `test_api_export_json`
**File:** `tests/test_api.py`
**Run:** `pytest tests/test_api.py::test_api_export_json`
**What:** Seed a session, call `GET /export/{id}.json`.
**Expected:** 200, valid JSON with `session_id` and `entries` fields.

### 13. `test_api_export_csv`
**File:** `tests/test_api.py`
**Run:** `pytest tests/test_api.py::test_api_export_csv`
**What:** Seed a session with 3 entries, call `GET /export/{id}.csv`.
**Expected:** 200, CSV with header row + 3 data rows.

### 14. `test_api_session_not_found`
**File:** `tests/test_api.py`
**Run:** `pytest tests/test_api.py::test_api_session_not_found`
**What:** Call `GET /sessions/does-not-exist`.
**Expected:** 404 response.
