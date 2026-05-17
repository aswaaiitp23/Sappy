"""
SQLite session persistence.

Schema
------
  messages(session_id TEXT, idx INTEGER, role TEXT, content TEXT)

`content` is JSON-encoded. It can be:
  - a plain string  (simple user text)
  - a list of dicts (assistant tool-call blocks, or tool_result blocks)

The serialisation step handles Pydantic model objects returned by the Anthropic SDK
so callers never have to think about it.
"""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(".agent_sessions.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the messages table if it does not exist yet."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                session_id  TEXT    NOT NULL,
                idx         INTEGER NOT NULL,
                role        TEXT    NOT NULL,
                content     TEXT    NOT NULL,
                PRIMARY KEY (session_id, idx)
            )
        """)


def _serialise_content(content) -> str:
    """
    Convert message content to a JSON string.

    The Anthropic SDK returns content blocks as Pydantic models. We call
    .model_dump() on any object that has it so json.dumps() always succeeds.
    """
    if isinstance(content, str):
        return json.dumps(content)

    if isinstance(content, list):
        cleaned = []
        for item in content:
            if hasattr(item, "model_dump"):
                cleaned.append(item.model_dump())
            elif isinstance(item, dict):
                cleaned.append(item)
            else:
                cleaned.append(str(item))
        return json.dumps(cleaned)

    # Fallback: stringify whatever came in
    return json.dumps(str(content))


def save_session(session_id: str, messages: list[dict]) -> None:
    """
    Persist the full message list for a session, replacing any previous rows.
    We delete-then-insert because the list can shrink (unlikely but safe).
    """
    with _connect() as conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.executemany(
            "INSERT INTO messages (session_id, idx, role, content) VALUES (?, ?, ?, ?)",
            [
                (session_id, idx, msg["role"], _serialise_content(msg["content"]))
                for idx, msg in enumerate(messages)
            ],
        )


def load_session(session_id: str) -> list[dict]:
    """Return the ordered message list for a session, or [] if not found."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY idx",
            (session_id,),
        ).fetchall()
    return [{"role": row["role"], "content": json.loads(row["content"])} for row in rows]
