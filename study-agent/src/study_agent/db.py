from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    goal TEXT NOT NULL,
    deadline TEXT,
    weekly_hours REAL NOT NULL DEFAULT 10,
    github_repo TEXT,
    course TEXT NOT NULL DEFAULT '',
    course_progress TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    estimate_minutes INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'doing', 'done', 'cancelled')),
    due_date TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS checkins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('morning', 'evening', 'weekly')),
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    kind TEXT NOT NULL,
    value TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(topic_id) REFERENCES topics(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS insight_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)")}
            if "topic_id" not in columns:
                conn.execute("ALTER TABLE sessions ADD COLUMN topic_id INTEGER")
            timestamp = now_iso()
            for name, description in (
                ("General", "General learning, planning, and projects"),
            ):
                conn.execute(
                    """
                    INSERT INTO topics(name, description, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(name) DO NOTHING
                    """,
                    (name, description, timestamp, timestamp),
                )
            default_topic = conn.execute(
                "SELECT id FROM topics WHERE name='General'"
            ).fetchone()
            conn.execute(
                "UPDATE sessions SET topic_id=? WHERE topic_id IS NULL",
                (default_topic["id"],),
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def save_profile(
        self,
        goal: str,
        deadline: str | None,
        weekly_hours: float,
        github_repo: str | None,
        course_progress: str = "",
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO profile
                    (id, goal, deadline, weekly_hours, github_repo, course_progress, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    goal=excluded.goal,
                    deadline=excluded.deadline,
                    weekly_hours=excluded.weekly_hours,
                    github_repo=excluded.github_repo,
                    course_progress=CASE
                        WHEN excluded.course_progress = '' THEN profile.course_progress
                        ELSE excluded.course_progress
                    END,
                    updated_at=excluded.updated_at
                """,
                (goal, deadline, weekly_hours, github_repo, course_progress, now_iso()),
            )

    def update_progress(self, progress: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE profile SET course_progress=?, updated_at=? WHERE id=1",
                (progress, now_iso()),
            )

    def profile(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM profile WHERE id=1").fetchone()
        return dict(row) if row else None

    def add_task(
        self,
        title: str,
        details: str,
        estimate_minutes: int,
        due_date: str | None,
    ) -> int:
        if estimate_minutes <= 0:
            raise ValueError("estimate_minutes must be positive")
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO tasks(title, details, estimate_minutes, due_date, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (title, details, estimate_minutes, due_date, now_iso()),
            )
            return int(cursor.lastrowid)

    def set_task_status(self, task_id: int, status: str) -> bool:
        if status not in {"planned", "doing", "done", "cancelled"}:
            raise ValueError(f"invalid task status: {status}")
        completed_at = now_iso() if status == "done" else None
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE tasks SET status=?, completed_at=? WHERE id=?",
                (status, completed_at, task_id),
            )
            return cursor.rowcount == 1

    def tasks(self, status: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        query = "SELECT * FROM tasks"
        params: list[Any] = []
        if status:
            query += " WHERE status=?"
            params.append(status)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def save_checkin(self, kind: str, payload: dict[str, Any]) -> int:
        if kind not in {"morning", "evening", "weekly"}:
            raise ValueError(f"invalid checkin kind: {kind}")
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO checkins(kind, payload, created_at) VALUES (?, ?, ?)",
                (kind, json.dumps(payload, ensure_ascii=False), now_iso()),
            )
            return int(cursor.lastrowid)

    def checkins(self, limit: int = 10) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM checkins ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item["payload"])
            result.append(item)
        return result

    def add_evidence(
        self, task_id: int | None, kind: str, value: str, note: str = ""
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO evidence(task_id, kind, value, note, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task_id, kind, value, note, now_iso()),
            )
            return int(cursor.lastrowid)

    def evidence(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM evidence ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def topics(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT t.*, COUNT(s.id) AS session_count
                FROM topics t
                LEFT JOIN sessions s ON s.topic_id = t.id
                GROUP BY t.id
                ORDER BY CASE t.name
                    WHEN 'General' THEN 0
                    ELSE 1
                END, t.updated_at DESC, t.name ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def topic(self, topic_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM topics WHERE id=?", (topic_id,)).fetchone()
        return dict(row) if row else None

    def default_topic_id(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM topics WHERE name='General'").fetchone()
        if not row:
            raise RuntimeError("General topic is missing")
        return int(row["id"])

    def create_topic(self, name: str, description: str = "") -> int:
        name = name.strip()
        if not name or len(name) > 80:
            raise ValueError("Topic name must be between 1 and 80 characters")
        timestamp = now_iso()
        try:
            with self.connect() as conn:
                cursor = conn.execute(
                    "INSERT INTO topics(name, description, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (name, description.strip()[:500], timestamp, timestamp),
                )
                return int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Topic already exists: {name}") from exc

    def rename_topic(self, topic_id: int, name: str) -> bool:
        current = self.topic(topic_id)
        if current and current["name"] == "General":
            raise ValueError("The General topic cannot be renamed")
        name = name.strip()
        if not name or len(name) > 80:
            raise ValueError("Topic name must be between 1 and 80 characters")
        try:
            with self.connect() as conn:
                cursor = conn.execute(
                    "UPDATE topics SET name=?, updated_at=? WHERE id=?",
                    (name, now_iso(), topic_id),
                )
                return cursor.rowcount == 1
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Topic already exists: {name}") from exc

    def delete_topic(self, topic_id: int) -> bool:
        topic = self.topic(topic_id)
        if not topic:
            return False
        if topic["name"] == "General":
            raise ValueError("The General topic cannot be deleted")
        general_id = self.default_topic_id()
        with self.connect() as conn:
            conn.execute(
                "UPDATE sessions SET topic_id=? WHERE topic_id=?",
                (general_id, topic_id),
            )
            cursor = conn.execute("DELETE FROM topics WHERE id=?", (topic_id,))
        return cursor.rowcount == 1

    def create_session(self, title: str = "New Chat", topic_id: int | None = None) -> int:
        timestamp = now_iso()
        topic_id = topic_id or self.default_topic_id()
        if not self.topic(topic_id):
            raise ValueError(f"Topic {topic_id} not found")
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO sessions(topic_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (topic_id, title.strip() or "New Chat", timestamp, timestamp),
            )
            return int(cursor.lastrowid)

    def sessions(self, limit: int = 50, topic_id: int | None = None) -> list[dict[str, Any]]:
        where = "WHERE s.topic_id=?" if topic_id is not None else ""
        params: list[Any] = [topic_id] if topic_id is not None else []
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT s.*, t.name AS topic_name, COUNT(m.id) AS message_count
                FROM sessions s
                LEFT JOIN topics t ON t.id = s.topic_id
                LEFT JOIN messages m ON m.session_id = s.id
                {where}
                GROUP BY s.id
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def session(self, session_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT s.*, t.name AS topic_name
                FROM sessions s LEFT JOIN topics t ON t.id=s.topic_id
                WHERE s.id=?
                """,
                (session_id,),
            ).fetchone()
        return dict(row) if row else None

    def add_message(self, session_id: int, role: str, content: str) -> int:
        if role not in {"user", "assistant"}:
            raise ValueError(f"invalid message role: {role}")
        timestamp = now_iso()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO messages(session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, content, timestamp),
            )
            conn.execute(
                "UPDATE sessions SET updated_at=? WHERE id=?",
                (timestamp, session_id),
            )
            return int(cursor.lastrowid)

    def messages(self, session_id: int, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM (
                    SELECT * FROM messages
                    WHERE session_id=?
                    ORDER BY id DESC
                    LIMIT ?
                ) ORDER BY id ASC
                """,
                (session_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def rename_session(self, session_id: int, title: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE sessions SET title=?, updated_at=? WHERE id=?",
                (title.strip()[:80] or "New Chat", now_iso(), session_id),
            )

    def fork_session(self, session_id: int) -> int:
        source = self.session(session_id)
        if not source:
            raise ValueError(f"Session {session_id} not found")
        timestamp = now_iso()
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO sessions(topic_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (source["topic_id"], f"Fork of {source['title']}"[:80], timestamp, timestamp),
            )
            fork_id = int(cursor.lastrowid)
            conn.execute(
                """
                INSERT INTO messages(session_id, role, content, created_at)
                SELECT ?, role, content, ? FROM messages
                WHERE session_id=? ORDER BY id ASC
                """,
                (fork_id, timestamp, session_id),
            )
        return fork_id

    def delete_session(self, session_id: int) -> bool:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
            return cursor.rowcount == 1

    def recent_messages(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM (
                    SELECT m.*, s.title AS session_title, t.name AS topic_name
                    FROM messages m
                    JOIN sessions s ON s.id = m.session_id
                    LEFT JOIN topics t ON t.id = s.topic_id
                    ORDER BY m.id DESC
                    LIMIT ?
                ) ORDER BY id ASC
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_insights(self, payload: dict[str, Any]) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO insight_snapshots(payload, created_at) VALUES (?, ?)",
                (json.dumps(payload, ensure_ascii=False), now_iso()),
            )
            return int(cursor.lastrowid)

    def latest_insights(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM insight_snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        return result

