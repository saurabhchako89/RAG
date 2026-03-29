import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path("data/rag.db")


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            filename TEXT,
            connector_id TEXT DEFAULT 'files',
            type TEXT,
            chunks INTEGER,
            pages_or_records INTEGER,
            storage TEXT DEFAULT 'local',
            object_name TEXT,
            ingested_at TEXT
        );
        CREATE TABLE IF NOT EXISTS chat_history (
            thread_id TEXT,
            turn INTEGER,
            role TEXT,
            content TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS sync_state (
            connector_id TEXT PRIMARY KEY,
            last_synced TEXT,
            status TEXT,
            doc_count INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    conn.close()


def _conn():
    return sqlite3.connect(DB_PATH)


def insert_document(record: dict):
    with _conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO documents
               (id, filename, connector_id, type, chunks, pages_or_records, storage, object_name, ingested_at)
               VALUES (:id, :filename, :connector_id, :type, :chunks, :pages_or_records, :storage, :object_name, :ingested_at)""",
            {**record, "ingested_at": datetime.now(timezone.utc).isoformat()},
        )


def list_documents(connector_id: str = None) -> list[dict]:
    with _conn() as conn:
        if connector_id:
            rows = conn.execute(
                "SELECT * FROM documents WHERE connector_id=? ORDER BY ingested_at DESC", (connector_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM documents ORDER BY ingested_at DESC").fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM documents LIMIT 0").description or []]
        if not cols:
            cols = ["id","filename","connector_id","type","chunks","pages_or_records","storage","object_name","ingested_at"]
        return [dict(zip(cols, r)) for r in rows]


def upsert_sync_state(connector_id: str, status: str, doc_count: int):
    with _conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO sync_state (connector_id, last_synced, status, doc_count)
               VALUES (?, ?, ?, ?)""",
            (connector_id, datetime.now(timezone.utc).isoformat(), status, doc_count),
        )


def get_sync_states() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM sync_state").fetchall()
        return [{"connector_id": r[0], "last_synced": r[1], "status": r[2], "doc_count": r[3]} for r in rows]


def append_chat_turn(thread_id: str, turn: int, role: str, content: str):
    with _conn() as conn:
        conn.execute(
            "INSERT INTO chat_history (thread_id, turn, role, content, created_at) VALUES (?,?,?,?,?)",
            (thread_id, turn, role, content, datetime.now(timezone.utc).isoformat()),
        )


def get_chat_history(thread_id: str, last_n: int = 10) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT role, content FROM chat_history
               WHERE thread_id=? ORDER BY turn DESC LIMIT ?""",
            (thread_id, last_n),
        ).fetchall()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]
