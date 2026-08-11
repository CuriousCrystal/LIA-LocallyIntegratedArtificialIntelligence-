import sqlite3
import json
import datetime as dt

from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS facts (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS diary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            entry TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Anything you drop in the library folder, chunked and embedded.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            title TEXT NOT NULL,
            page INTEGER,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding TEXT NOT NULL,
            mtime REAL NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_path ON documents(path)")

    # Spoken alarms and timers -- stored so one survives a restart: set "wake
    # me up at 7am" before closing the laptop, and it still fires the next
    # time she's running, even if that's a fresh process.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS alarms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fire_at TEXT NOT NULL,
            label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            fired INTEGER NOT NULL DEFAULT 0
        )
    """)

    # A single enrolled voiceprint, averaged in over each enrollment so it
    # gets more representative rather than being overwritten. One row, always
    # id=1 -- there's only ever one person she's trying to recognise.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS voice_profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            embedding TEXT NOT NULL,
            sample_count INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


def upsert_fact(key: str, value: str):
    conn = get_conn()
    conn.execute(
        """INSERT INTO facts (key, value, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
        (key, value, now()),
    )
    conn.commit()
    conn.close()


def get_all_facts() -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM facts").fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}


def insert_memory(session_id: str, role: str, content: str, embedding: list[float]):
    conn = get_conn()
    conn.execute(
        "INSERT INTO memories (session_id, role, content, embedding, created_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, role, content, json.dumps(embedding), now()),
    )
    conn.commit()
    conn.close()


def all_memories(role: str | None = None):
    """All stored turns, optionally just one speaker's.

    Retrieval passes role="user": Lia's own replies would otherwise compete for
    the handful of recall slots, and she reads them back as things she was told.
    """
    sql = "SELECT id, session_id, role, content, embedding, created_at FROM memories"
    params = ()
    if role is not None:
        sql += " WHERE role = ?"
        params = (role,)

    conn = get_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def indexed_documents() -> dict:
    """{path: mtime} for everything already in the library index."""
    conn = get_conn()
    rows = conn.execute("SELECT path, MAX(mtime) AS mtime FROM documents GROUP BY path").fetchall()
    conn.close()
    return {row["path"]: row["mtime"] for row in rows}


def forget_document(path: str):
    conn = get_conn()
    conn.execute("DELETE FROM documents WHERE path = ?", (path,))
    conn.commit()
    conn.close()


def insert_document_chunks(rows: list[tuple]):
    """rows of (path, title, page, chunk_index, content, embedding_json, mtime)."""
    conn = get_conn()
    conn.executemany(
        """INSERT INTO documents (path, title, page, chunk_index, content, embedding, mtime, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [r + (now(),) for r in rows],
    )
    conn.commit()
    conn.close()


def unfinished_chunk_count(path: str) -> int:
    """How many passages of this document were written by a run that never
    finished. Rows carry mtime 0 until the whole file is indexed, so this is
    both the "was it interrupted" test and the place to resume from."""
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM documents WHERE path = ? AND mtime = 0", (path,)
    ).fetchone()
    conn.close()
    return row["n"]


def any_unfinished_documents() -> bool:
    """Is some document part-read anywhere? True while a scan is in flight.

    Deliberately asked of the database rather than tracked in memory: the scan
    may be running in another process entirely, and an in-process flag is
    invisible to it. Reading the library was stalled for nine minutes at a time
    by exactly that -- the tray app released the models from VRAM because, as
    far as its own flag knew, nothing was using them."""
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM documents WHERE mtime = 0 LIMIT 1"
    ).fetchone()
    conn.close()
    return row is not None


def finish_document(path: str, mtime: float):
    """Stamp a document's passages with the file's real mtime, marking it fully
    read. Until this runs, indexed_documents() reports 0 for it and pending()
    keeps offering it."""
    conn = get_conn()
    conn.execute("UPDATE documents SET mtime = ? WHERE path = ?", (mtime, path))
    conn.commit()
    conn.close()


def all_document_chunks():
    conn = get_conn()
    rows = conn.execute(
        "SELECT title, page, content, embedding FROM documents"
    ).fetchall()
    conn.close()
    return rows


def document_titles() -> list[tuple[str, int]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT title, COUNT(*) AS chunks FROM documents GROUP BY title ORDER BY title"
    ).fetchall()
    conn.close()
    return [(row["title"], row["chunks"]) for row in rows]


def insert_diary_entry(session_id: str, entry: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO diary (session_id, entry, created_at) VALUES (?, ?, ?)",
        (session_id, entry, now()),
    )
    conn.commit()
    conn.close()


def recent_diary_entries(limit: int = 5):
    conn = get_conn()
    rows = conn.execute(
        "SELECT session_id, entry, created_at FROM diary ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows


def insert_alarm(fire_at: str, label: str) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO alarms (fire_at, label, created_at, fired) VALUES (?, ?, ?, 0)",
        (fire_at, label, now()),
    )
    conn.commit()
    alarm_id = cur.lastrowid
    conn.close()
    return alarm_id


def due_alarms(now_iso: str):
    """Unfired alarms whose time has come."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, fire_at, label FROM alarms WHERE fired = 0 AND fire_at <= ?", (now_iso,)
    ).fetchall()
    conn.close()
    return rows


def mark_alarm_fired(alarm_id: int):
    conn = get_conn()
    conn.execute("UPDATE alarms SET fired = 1 WHERE id = ?", (alarm_id,))
    conn.commit()
    conn.close()


def pending_alarms():
    """Unfired alarms, soonest first."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, fire_at, label FROM alarms WHERE fired = 0 ORDER BY fire_at"
    ).fetchall()
    conn.close()
    return rows


def cancel_all_alarms() -> int:
    conn = get_conn()
    cur = conn.execute("UPDATE alarms SET fired = 1 WHERE fired = 0")
    conn.commit()
    n = cur.rowcount
    conn.close()
    return n


def get_voice_profile() -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT embedding, sample_count FROM voice_profile WHERE id = 1").fetchone()
    conn.close()
    if row is None:
        return None
    return {"embedding": json.loads(row["embedding"]), "sample_count": row["sample_count"]}


def save_voice_profile(embedding: list, sample_count: int):
    conn = get_conn()
    conn.execute(
        """INSERT INTO voice_profile (id, embedding, sample_count, updated_at) VALUES (1, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET embedding=excluded.embedding,
               sample_count=excluded.sample_count, updated_at=excluded.updated_at""",
        (json.dumps(embedding), sample_count, now()),
    )
    conn.commit()
    conn.close()


def clear_voice_profile():
    conn = get_conn()
    conn.execute("DELETE FROM voice_profile WHERE id = 1")
    conn.commit()
    conn.close()
