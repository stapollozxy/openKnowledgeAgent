from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


BUNDLE_FORMAT = "open-knowledge-agent"
BUNDLE_VERSION = 1
MAX_BUNDLE_BYTES = 2 * 1024 * 1024 * 1024


def _active_database(source: Path) -> tuple[Path, Path | None]:
    source = source.expanduser().resolve()
    if source.is_file():
        return source, None
    candidates = (source / ".study-agent" / "agent.db", source / "agent.db")
    database = next((candidate for candidate in candidates if candidate.is_file()), None)
    if not database:
        raise ValueError("The selected folder does not contain an active agent.db database.")
    knowledge = source / "knowledge"
    return database, knowledge if knowledge.is_dir() else None


def _snapshot_database(source: Path, destination: Path) -> None:
    source_connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()


def _verify_database(path: Path) -> None:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        connection.close()
    if not result or result[0] != "ok":
        raise ValueError("The imported database failed its integrity check.")
    required = {"profile", "topics", "sessions", "messages"}
    if not required.issubset(tables):
        raise ValueError("The bundle does not contain a compatible agent database.")


def export_bundle(source: Path, output: Path) -> dict[str, Any]:
    database, knowledge = _active_database(source)
    output = output.expanduser().resolve()
    if output.suffix.lower() != ".okagent":
        output = output.with_suffix(".okagent")
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="open-knowledge-export-") as temporary:
        snapshot = Path(temporary) / "agent.db"
        _snapshot_database(database, snapshot)
        _verify_database(snapshot)
        knowledge_files = [
            path
            for path in sorted(knowledge.rglob("*"))
            if knowledge and path.is_file() and not path.is_symlink() and path.name != ".DS_Store"
        ] if knowledge else []
        manifest = {
            "format": BUNDLE_FORMAT,
            "version": BUNDLE_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "contains": {"database": True, "knowledge": bool(knowledge_files)},
        }
        temporary_output = output.with_suffix(output.suffix + ".tmp")
        with zipfile.ZipFile(
            temporary_output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
            archive.write(snapshot, "state/agent.db")
            for path in knowledge_files:
                archive.write(path, (Path("knowledge") / path.relative_to(knowledge)).as_posix())
        os.replace(temporary_output, output)
    return {"path": str(output), **manifest["contains"]}


def _validated_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    if len(members) > 10_000:
        raise ValueError("The data bundle contains too many files.")
    if sum(item.file_size for item in members) > MAX_BUNDLE_BYTES:
        raise ValueError("The data bundle is too large.")
    for item in members:
        path = PurePosixPath(item.filename)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("The data bundle contains an unsafe path.")
        file_type = (item.external_attr >> 16) & 0o170000
        if file_type == stat.S_IFLNK:
            raise ValueError("The data bundle contains an unsafe symbolic link.")
        allowed = item.filename == "manifest.json" or path.parts[:1] in {
            ("state",),
            ("knowledge",),
        }
        if not allowed:
            raise ValueError(f"Unexpected file in data bundle: {item.filename}")
    return members


def import_bundle(bundle: Path, database: Path, knowledge: Path) -> dict[str, Any]:
    bundle = bundle.expanduser().resolve()
    if not bundle.is_file():
        raise ValueError("The selected data bundle does not exist.")
    database = database.expanduser().resolve()
    knowledge = knowledge.expanduser().resolve()
    backup_root = database.parent / "import-backups" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")

    with tempfile.TemporaryDirectory(prefix="open-knowledge-import-") as temporary:
        extracted = Path(temporary)
        try:
            with zipfile.ZipFile(bundle, "r") as archive:
                _validated_members(archive)
                manifest = json.loads(archive.read("manifest.json"))
                if manifest.get("format") != BUNDLE_FORMAT or manifest.get("version") != BUNDLE_VERSION:
                    raise ValueError("This data bundle format is not supported.")
                archive.extractall(extracted)
        except (KeyError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
            raise ValueError("The selected file is not a valid Open Knowledge Agent bundle.") from exc

        imported_database = extracted / "state" / "agent.db"
        if not imported_database.is_file():
            raise ValueError("The data bundle is missing its agent database.")
        _verify_database(imported_database)

        backup_root.mkdir(parents=True, exist_ok=False)
        if database.is_file():
            shutil.copy2(database, backup_root / "agent.db")
        if knowledge.is_dir():
            shutil.copytree(knowledge, backup_root / "knowledge")

        database.parent.mkdir(parents=True, exist_ok=True)
        staged_database = database.with_suffix(database.suffix + ".importing")
        shutil.copy2(imported_database, staged_database)
        os.replace(staged_database, database)

        imported_knowledge = extracted / "knowledge"
        knowledge_imported = imported_knowledge.is_dir()
        if knowledge.exists():
            shutil.rmtree(knowledge)
        if knowledge_imported:
            shutil.copytree(imported_knowledge, knowledge)

    return {
        "imported": True,
        "backup_path": str(backup_root),
        "knowledge_imported": knowledge_imported,
    }
