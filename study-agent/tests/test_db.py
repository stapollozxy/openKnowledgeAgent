from pathlib import Path
import sqlite3

import pytest

from study_agent.cli import require_profile
from study_agent.db import Store


def test_first_use_creates_only_a_blank_profile_and_general_topic(tmp_path: Path) -> None:
    db = Store(tmp_path / "agent.db")

    profile = require_profile(db)

    assert profile["goal"] == ""
    assert profile["deadline"] is None
    assert profile["github_repo"] is None
    assert profile["course"] == ""
    assert profile["course_progress"] == ""
    assert [topic["name"] for topic in db.topics()] == ["General"]
    assert db.sessions() == []
    assert db.recent_messages() == []


def test_profile_tasks_checkins_and_evidence(tmp_path: Path) -> None:
    db = Store(tmp_path / "agent.db")
    db.save_profile("test-goal", "2099-01-01", 12, "example/repository", "stage-one")
    assert db.profile()["github_repo"] == "example/repository"

    task_id = db.add_task("test-task", "test-details", 45, "2099-01-02")
    assert db.tasks()[0]["status"] == "planned"
    assert db.set_task_status(task_id, "done") is True
    assert db.tasks()[0]["status"] == "done"

    db.save_checkin("evening", {"completed": "test-result"})
    assert db.checkins()[0]["payload"]["completed"] == "test-result"

    evidence_id = db.add_evidence(task_id, "test-kind", "test-value", "test-note")
    assert evidence_id > 0
    assert db.evidence()[0]["value"] == "test-value"


def test_empty_progress_does_not_erase_existing_progress(tmp_path: Path) -> None:
    db = Store(tmp_path / "agent.db")
    db.save_profile("first-goal", None, 10, None, "stage-two")
    db.save_profile("second-goal", None, 8, None, "")
    assert db.profile()["course_progress"] == "stage-two"


def test_confirmed_profile_fields_are_updated_and_unknown_fields_are_rejected(tmp_path: Path) -> None:
    db = Store(tmp_path / "agent.db")
    db.save_profile("", None, 10, None)

    profile = db.update_profile({
        "course": "Distributed Systems",
        "course_progress": "Chapter 3",
        "goal": "Build a replicated key-value store",
    })

    assert profile["course"] == "Distributed Systems"
    assert profile["course_progress"] == "Chapter 3"
    assert profile["goal"] == "Build a replicated key-value store"
    with pytest.raises(ValueError, match="not writable"):
        db.update_profile({"api_key": "must-never-be-written"})


def test_existing_profile_database_is_migrated_with_a_course_column(tmp_path: Path) -> None:
    path = tmp_path / "agent.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE profile (
                id INTEGER PRIMARY KEY,
                goal TEXT NOT NULL,
                deadline TEXT,
                weekly_hours REAL NOT NULL,
                github_repo TEXT,
                course_progress TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO profile VALUES (1, 'goal', NULL, 10, NULL, 'chapter 1', 'now')"
        )

    db = Store(path)

    assert db.profile()["course"] == ""
    assert db.profile()["course_progress"] == "chapter 1"


def test_chat_sessions_persist_messages(tmp_path: Path) -> None:
    db = Store(tmp_path / "agent.db")
    session_id = db.create_session("test-session")
    db.add_message(session_id, "user", "test-user-message")
    db.add_message(session_id, "assistant", "test-assistant-message")

    assert db.sessions()[0]["message_count"] == 2
    assert [item["role"] for item in db.messages(session_id)] == ["user", "assistant"]


def test_insights_snapshot_and_recent_messages(tmp_path: Path) -> None:
    db = Store(tmp_path / "agent.db")
    session_id = db.create_session("test-session")
    db.add_message(session_id, "user", "test-question")
    db.save_insights({"overview": "test-overview"})

    assert db.recent_messages()[0]["session_title"] == "test-session"
    assert db.latest_insights()["payload"]["overview"] == "test-overview"


def test_session_fork_and_delete(tmp_path: Path) -> None:
    db = Store(tmp_path / "agent.db")
    original = db.create_session("test-session")
    db.add_message(original, "user", "test-question")
    db.add_message(original, "assistant", "test-answer")

    forked = db.fork_session(original)
    assert forked != original
    assert [message["content"] for message in db.messages(forked)] == [
        "test-question",
        "test-answer",
    ]
    assert db.delete_session(original) is True
    assert db.session(original) is None
    assert db.messages(original) == []


def test_topics_group_sessions_and_safe_delete(tmp_path: Path) -> None:
    db = Store(tmp_path / "agent.db")
    names = {topic["name"] for topic in db.topics()}
    assert names == {"General"}

    topic_id = db.create_topic("test-topic")
    session_id = db.create_session("test-session", topic_id=topic_id)
    assert db.sessions(topic_id=topic_id)[0]["title"] == "test-session"
    assert db.rename_topic(topic_id, "renamed-test-topic") is True
    assert db.session(session_id)["topic_name"] == "renamed-test-topic"

    assert db.delete_topic(topic_id) is True
    assert db.session(session_id)["topic_name"] == "General"

