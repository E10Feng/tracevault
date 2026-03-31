# TraceVault

TraceVault is a Python library wrapping LangGraph/LangChain agents to produce tamper-proof audit trails with HMAC-chained entries and LLM-generated summaries.

## Features

- HMAC-SHA256 chained audit trail entries
- LangChain callback handler integration
- LLM-generated step summaries via GPT-4o-mini
- FastAPI REST API with JSON/CSV export
- Jinja2 web UI for browsing sessions
- SQLite storage with threading support
- CLI for serving, verifying, and exporting

## Installation

```bash
pip install -r requirements.txt
pip install -e .
```

## Quick Start

```python
from tracevault import TraceVaultCallbackHandler, TraceStorage, TraceSession
import uuid

storage = TraceStorage("my_traces.db")
session_id = str(uuid.uuid4())

handler = TraceVaultCallbackHandler(
    session_id=session_id,
    agent_name="my-agent",
    storage=storage,
    secret="my-secret",
)

# Use as a LangChain callback
from langchain.chains import LLMChain
chain = LLMChain(llm=my_llm, prompt=my_prompt, callbacks=[handler])
```

## CLI

```bash
# Start the web server
tracevault serve --port 8000 --db tracevault.db

# Verify a session chain
tracevault verify <session_id>

# Export a session
tracevault export <session_id> --format json
tracevault export <session_id> --format csv
```

## API Endpoints

- `GET /sessions` - List all sessions
- `GET /sessions/{session_id}` - Get session details with chain validity
- `GET /sessions/{session_id}/verify` - Verify chain integrity
- `GET /sessions/{session_id}/summary` - Get LLM-generated summary
- `GET /export/{session_id}.json` - Export as JSON
- `GET /export/{session_id}.csv` - Export as CSV
- `GET /ui` - Web UI sessions list
- `GET /ui/{session_id}` - Web UI session detail

## Environment Variables

```
OPENAI_API_KEY=your-openai-key
TRACEVAULT_SECRET=your-hmac-secret
TRACEVAULT_DB=tracevault.db
```
