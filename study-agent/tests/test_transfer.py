import sqlite3
import zipfile
from pathlib import Path

import pytest

from study_agent.db import Store
from study_agent.transfer import export_bundle, import_bundle


def test_export_and_import_round_trip_without_credentials(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source_store = Store(source / ".study-agent" / "agent.db")
    source_store.save_profile("test-goal", None, 10, None)
    topic = source_store.create_topic("test-topic")
    session = source_store.create_session("test-session", topic_id=topic)
    source_store.add_message(session, "user", "test-message")
    (source / "knowledge").mkdir()
    (source / "knowledge" / "note.md").write_text("test-note", encoding="utf-8")
    (source / ".env").write_text("OPENAI_API_KEY=test-secret", encoding="utf-8")

    bundle = tmp_path / "export.okagent"
    export_bundle(source, bundle)

    with zipfile.ZipFile(bundle) as archive:
        assert sorted(archive.namelist()) == [
            "knowledge/note.md",
            "manifest.json",
            "state/agent.db",
        ]
        assert b"test-secret" not in bundle.read_bytes()

    destination_store = Store(tmp_path / "destination" / "agent.db")
    destination_store.save_profile("replace-me", None, 10, None)
    destination_knowledge = tmp_path / "destination-knowledge"
    result = import_bundle(bundle, destination_store.path, destination_knowledge)

    imported = Store(destination_store.path)
    assert imported.profile()["goal"] == "test-goal"
    assert imported.messages(session)[0]["content"] == "test-message"
    assert (destination_knowledge / "note.md").read_text(encoding="utf-8") == "test-note"
    assert Path(result["backup_path"], "agent.db").is_file()


def test_import_rejects_path_traversal(tmp_path: Path) -> None:
    bundle = tmp_path / "unsafe.okagent"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("manifest.json", '{"format":"open-knowledge-agent","version":1}')
        archive.writestr("../outside", "bad")

    with pytest.raises(ValueError, match="unsafe path"):
        import_bundle(bundle, tmp_path / "agent.db", tmp_path / "knowledge")


def test_import_rejects_unrelated_sqlite_database(tmp_path: Path) -> None:
    unrelated = tmp_path / "unrelated.db"
    with sqlite3.connect(unrelated) as connection:
        connection.execute("CREATE TABLE unrelated(value TEXT)")
    bundle = tmp_path / "invalid.okagent"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("manifest.json", '{"format":"open-knowledge-agent","version":1}')
        archive.write(unrelated, "state/agent.db")

    with pytest.raises(ValueError, match="compatible"):
        import_bundle(bundle, tmp_path / "agent.db", tmp_path / "knowledge")


def test_import_replaces_stale_knowledge_when_bundle_has_none(tmp_path: Path) -> None:
    source = tmp_path / "source"
    Store(source / ".study-agent" / "agent.db")
    bundle = tmp_path / "without-knowledge.okagent"
    export_bundle(source, bundle)

    destination_store = Store(tmp_path / "destination" / "agent.db")
    destination_knowledge = tmp_path / "destination-knowledge"
    destination_knowledge.mkdir()
    (destination_knowledge / "stale.md").write_text("stale", encoding="utf-8")

    result = import_bundle(bundle, destination_store.path, destination_knowledge)

    assert result["knowledge_imported"] is False
    assert not destination_knowledge.exists()
    assert Path(result["backup_path"], "knowledge", "stale.md").is_file()
