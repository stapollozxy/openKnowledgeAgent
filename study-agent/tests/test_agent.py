from pathlib import Path

from study_agent.agent import build_agent
from study_agent.db import Store


def test_agent_builds_with_expected_tools(tmp_path: Path) -> None:
    db = Store(tmp_path / "agent.db")
    db.save_profile("test-goal", None, 10, None)

    agent = build_agent(db)

    assert agent.name == "General Study Agent"
    assert len(agent.tools) == 10
    assert "get_system_time" in {tool.name for tool in agent.tools}

