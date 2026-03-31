from __future__ import annotations
import json
import sqlite3
import threading
from typing import Optional
from datetime import datetime, timezone

from .models import TraceEntry, TraceSession


class TraceStorage:
    def __init__(self, db_path: str = "tracevault.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        # For :memory: databases, keep a single persistent connection
        self._memory_conn: Optional[sqlite3.Connection] = None
        if db_path == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._memory_conn is not None:
            return self._memory_conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _close_conn(self, conn: sqlite3.Connection):
        """Close connection only if it's not the shared memory connection."""
        if conn is not self._memory_conn:
            conn.close()

    def _init_db(self):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY,
                        agent_name TEXT,
                        created_at TEXT,
                        metadata TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS trace_entries (
                        id TEXT PRIMARY KEY,
                        session_id TEXT,
                        step_index INTEGER,
                        entry_type TEXT,
                        payload TEXT,
                        summary TEXT,
                        hmac_hash TEXT,
                        prev_hash TEXT,
                        created_at TEXT
                    )
                """)
                conn.commit()
            finally:
                self._close_conn(conn)

    def create_session(self, session: TraceSession):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO sessions (session_id, agent_name, created_at, metadata) VALUES (?, ?, ?, ?)",
                    (session.session_id, session.agent_name, session.created_at, json.dumps(session.metadata))
                )
                conn.commit()
            finally:
                self._close_conn(conn)

    def add_entry(self, entry: TraceEntry):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO trace_entries
                    (id, session_id, step_index, entry_type, payload, summary, hmac_hash, prev_hash, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        entry.id,
                        entry.session_id,
                        entry.step_index,
                        entry.entry_type,
                        json.dumps(entry.payload),
                        entry.summary,
                        entry.hmac_hash,
                        entry.prev_hash,
                        entry.created_at,
                    )
                )
                conn.commit()
            finally:
                self._close_conn(conn)

    def get_session(self, session_id: str) -> Optional[TraceSession]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
                ).fetchone()
                if row is None:
                    return None
                return TraceSession(
                    session_id=row["session_id"],
                    agent_name=row["agent_name"],
                    created_at=row["created_at"],
                    metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                )
            finally:
                self._close_conn(conn)

    def get_entries(self, session_id: str) -> list[TraceEntry]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM trace_entries WHERE session_id = ? ORDER BY step_index ASC",
                    (session_id,)
                ).fetchall()
                return [
                    TraceEntry(
                        id=row["id"],
                        session_id=row["session_id"],
                        step_index=row["step_index"],
                        entry_type=row["entry_type"],
                        payload=json.loads(row["payload"]) if row["payload"] else {},
                        summary=row["summary"],
                        hmac_hash=row["hmac_hash"],
                        prev_hash=row["prev_hash"],
                        created_at=row["created_at"],
                    )
                    for row in rows
                ]
            finally:
                self._close_conn(conn)

    def get_all_sessions(self) -> list[dict]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute("""
                    SELECT s.session_id, s.agent_name, s.created_at, s.metadata,
                           COUNT(t.id) as step_count
                    FROM sessions s
                    LEFT JOIN trace_entries t ON s.session_id = t.session_id
                    GROUP BY s.session_id
                    ORDER BY s.created_at DESC
                """).fetchall()
                return [
                    {
                        "session_id": row["session_id"],
                        "agent_name": row["agent_name"],
                        "created_at": row["created_at"],
                        "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                        "step_count": row["step_count"],
                    }
                    for row in rows
                ]
            finally:
                self._close_conn(conn)

    def update_entry_summary(self, entry_id: str, summary: str):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE trace_entries SET summary = ? WHERE id = ?",
                    (summary, entry_id)
                )
                conn.commit()
            finally:
                self._close_conn(conn)

    def mutate_entry_payload_for_testing(self, entry_id: str, new_payload: dict):
        """For test use only - directly mutates payload without updating HMAC."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE trace_entries SET payload = ? WHERE id = ?",
                    (json.dumps(new_payload), entry_id)
                )
                conn.commit()
            finally:
                self._close_conn(conn)
