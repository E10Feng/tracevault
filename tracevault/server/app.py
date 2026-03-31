from __future__ import annotations
import csv
import io
import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request

from ..chain import verify_chain
from ..storage import TraceStorage
from ..summarizer import Summarizer

app = FastAPI(title="TraceVault", version="0.1.0")

# Templates and static files
_HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(_HERE / "templates"))

app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")

# Default storage (can be overridden in tests)
_default_db_path = os.environ.get("TRACEVAULT_DB", "tracevault.db")
_default_secret = os.environ.get("TRACEVAULT_SECRET", "test-secret")


def get_storage() -> TraceStorage:
    return TraceStorage(_default_db_path)


def get_secret() -> str:
    return _default_secret


# --- REST API ---

@app.get("/sessions")
def list_sessions(storage: TraceStorage = Depends(get_storage)):
    sessions = storage.get_all_sessions()
    return {"sessions": sessions}


@app.get("/sessions/{session_id}")
def get_session(
    session_id: str,
    storage: TraceStorage = Depends(get_storage),
    secret: str = Depends(get_secret),
):
    session = storage.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    entries = storage.get_entries(session_id)
    chain_valid, _ = verify_chain(entries, secret)
    return {
        "session_id": session.session_id,
        "agent_name": session.agent_name,
        "created_at": session.created_at,
        "chain_valid": chain_valid,
        "entries": [e.model_dump() for e in entries],
    }


@app.get("/sessions/{session_id}/summary")
def get_session_summary(
    session_id: str,
    storage: TraceStorage = Depends(get_storage),
):
    session = storage.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    entries = storage.get_entries(session_id)
    summarizer = Summarizer()
    summary = summarizer.summarize_session(entries)
    return {"session_id": session_id, "summary": summary}


@app.get("/sessions/{session_id}/verify")
def verify_session(
    session_id: str,
    storage: TraceStorage = Depends(get_storage),
    secret: str = Depends(get_secret),
):
    session = storage.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    entries = storage.get_entries(session_id)
    chain_valid, broken_at_step = verify_chain(entries, secret)
    return {
        "session_id": session_id,
        "chain_valid": chain_valid,
        "broken_at_step": broken_at_step,
    }


@app.get("/export/{session_id}.json")
def export_json(
    session_id: str,
    storage: TraceStorage = Depends(get_storage),
):
    session = storage.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    entries = storage.get_entries(session_id)
    data = {
        "session_id": session_id,
        "agent_name": session.agent_name,
        "created_at": session.created_at,
        "metadata": session.metadata,
        "entries": [e.model_dump() for e in entries],
    }
    return JSONResponse(content=data)


@app.get("/export/{session_id}.csv")
def export_csv(
    session_id: str,
    storage: TraceStorage = Depends(get_storage),
):
    session = storage.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    entries = storage.get_entries(session_id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "session_id", "entry_id", "step_index", "entry_type",
        "summary", "hmac_hash", "prev_hash", "created_at", "payload"
    ])
    for entry in entries:
        writer.writerow([
            entry.session_id,
            entry.id,
            entry.step_index,
            entry.entry_type,
            entry.summary or "",
            entry.hmac_hash,
            entry.prev_hash,
            entry.created_at,
            json.dumps(entry.payload),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={session_id}.csv"},
    )


# --- UI Routes ---

@app.get("/ui", response_class=HTMLResponse)
def ui_sessions(request: Request, storage: TraceStorage = Depends(get_storage)):
    sessions = storage.get_all_sessions()
    return templates.TemplateResponse(
        "sessions.html", {"request": request, "sessions": sessions}
    )


@app.get("/ui/{session_id}", response_class=HTMLResponse)
def ui_session_detail(
    request: Request,
    session_id: str,
    storage: TraceStorage = Depends(get_storage),
    secret: str = Depends(get_secret),
):
    session = storage.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    entries = storage.get_entries(session_id)
    chain_valid, _ = verify_chain(entries, secret)
    return templates.TemplateResponse(
        "session_detail.html",
        {
            "request": request,
            "session": session,
            "entries": entries,
            "chain_valid": chain_valid,
        },
    )
