import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "scripts" / "oka"


def run_bridge(app_support: Path, *args: str) -> str:
    environment = os.environ.copy()
    environment["OPEN_KNOWLEDGE_AGENT_APP_SUPPORT"] = str(app_support)
    result = subprocess.run(
        [str(BRIDGE), *args],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_codex_bridge_uses_shared_app_state_without_an_api_key(tmp_path: Path) -> None:
    app_support = tmp_path / "Open Knowledge Agent"
    run_bridge(app_support, "init", "--course", "Test Course", "--goal", "Test Goal")

    topics = json.loads(run_bridge(app_support, "topics"))
    task = json.loads(run_bridge(
        app_support,
        "task-new",
        "--title",
        "Build a test",
        "--minutes",
        "30",
    ))
    evidence = json.loads(run_bridge(
        app_support,
        "evidence-add",
        "--kind",
        "test",
        "--value",
        "tests passed",
        "--task",
        str(task["task_id"]),
    ))
    completed = json.loads(run_bridge(
        app_support,
        "task-complete",
        "--task",
        str(task["task_id"]),
    ))

    assert (app_support / "data" / "agent.db").is_file()
    assert [topic["name"] for topic in topics] == ["General"]
    assert evidence["recorded"] is True
    assert completed == {"task_id": task["task_id"], "status": "done"}
