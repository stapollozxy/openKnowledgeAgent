from pathlib import Path

from study_agent.db import Store
from study_agent.knowledge import export_knowledge


def test_export_knowledge_writes_portable_markdown(tmp_path: Path) -> None:
    db = Store(tmp_path / "agent.db")
    db.save_profile("test-goal", None, 10, None)
    session_id = db.create_session("test-session")
    db.add_message(session_id, "user", "test-question")
    payload = {
        "overview": "test-overview",
        "strengths": ["test-strength"],
        "gaps": [],
        "meaningful_questions": [{"question": "test-question", "review_prompt": "test-review-prompt"}],
        "next_learning": [{"priority": 1, "topic": "test-topic", "next_action": "test-action"}],
        "industry_projects": [{"name": "test-project", "metrics": ["test-metric"]}],
    }

    export_knowledge(db, payload, tmp_path / "knowledge")

    assert (tmp_path / "knowledge" / "README.md").is_file()
    assert (tmp_path / "knowledge" / "knowledge-graph.md").is_file()
    assert "test-question" in (tmp_path / "knowledge" / "questions.md").read_text()
    assert list((tmp_path / "knowledge" / "sessions").rglob("*.md"))
