import sqlite3
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path.home() / ".tiktok-flamekeeper" / "streak.db"


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sent_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT NOT NULL,
            message TEXT NOT NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_target_sent ON sent_messages(target, sent_at)
    """)
    conn.commit()
    conn.close()


def log_sent(target: str, message: str):
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO sent_messages (target, message) VALUES (?, ?)",
        (target, message),
    )
    conn.commit()
    conn.close()


def pick_message(target: str, messages: list[str]) -> str:
    """Least recently used message, weighted toward freshness."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.execute(
        "SELECT message, sent_at FROM sent_messages WHERE target = ? ORDER BY sent_at DESC",
        (target,),
    )
    recent = [row[0] for row in cursor.fetchall()]
    conn.close()

    seven_days_ago = datetime.now() - timedelta(days=7)
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.execute(
        "SELECT message FROM sent_messages WHERE target = ? AND sent_at > ?",
        (target, seven_days_ago.isoformat()),
    )
    used_recently = {row[0] for row in cursor.fetchall()}
    conn.close()

    available = [m for m in messages if m not in used_recently]
    if not available:
        available = messages

    if len(available) > 1 and recent:
        last_used = recent[0]
        if last_used in available and len(available) > 1:
            available.remove(last_used)

    return random.choice(available)


def get_streak_log(target: str = None, limit: int = 30):
    conn = sqlite3.connect(str(DB_PATH))
    if target:
        rows = conn.execute(
            "SELECT target, message, sent_at FROM sent_messages WHERE target = ? ORDER BY sent_at DESC LIMIT ?",
            (target, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT target, message, sent_at FROM sent_messages ORDER BY sent_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return rows
