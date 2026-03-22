"""SQLite database for deduplication and state persistence."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "apartments.db"
RETENTION_DAYS = 30


@contextmanager
def _get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create the table if it doesn't exist yet."""
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS apartments (
                id         TEXT PRIMARY KEY,
                portal     TEXT NOT NULL,
                title      TEXT,
                price      TEXT,
                url        TEXT,
                timestamp  TEXT NOT NULL
            )
            """
        )


def exists(listing_id: str) -> bool:
    """Check if a listing already exists in the DB."""
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM apartments WHERE id = ? LIMIT 1",
            (listing_id,),
        ).fetchone()
    return row is not None


def insert(listing_id: str, portal: str, title: str, price: str, url: str) -> None:
    """Store a new listing."""
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO apartments (id, portal, title, price, url, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (listing_id, portal, title, price, url, datetime.now(timezone.utc).isoformat()),
        )


def cleanup_old_entries() -> int:
    """Delete entries older than RETENTION_DAYS. Returns the number of deleted rows."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
    with _get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM apartments WHERE timestamp < ?",
            (cutoff,),
        )
    return cursor.rowcount
