import sqlite3
import json

DB_PATH = "sessions.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            messages TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_session(session_id: str, messages: list):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO sessions (id, messages, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            messages = excluded.messages,
            updated_at = CURRENT_TIMESTAMP
    """, (session_id, json.dumps(messages)))
    conn.commit()
    conn.close()

def load_session(session_id: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT messages FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    conn.close()
    return json.loads(row[0]) if row else []