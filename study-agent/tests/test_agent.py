from pathlib import Path

from study_agent.agent import build_agent, extract_profile_update
from study_agent.db import Store


def test_agent_builds_with_expected_tools(tmp_path: Path) -> None:
    db = Store(tmp_path / "agent.db")
    db.save_profile("test-goal", None, 10, None)

    agent = build_agent(db)

    assert agent.name == "General Study Agent"
    assert len(agent.tools) == 10
    assert "get_system_time" in {tool.name for tool in agent.tools}


def test_profile_update_proposal_is_extracted_and_never_treats_placeholders_as_data() -> None:
    response, changes = extract_profile_update(
        'I can save this after confirmation.\n'
        '<profile_update>{"course":"Distributed Systems",'
        '"course_progress":"[待填写当前章节]","goal":"Build a lab"}</profile_update>'
    )

    assert response == "I can save this after confirmation."
    assert changes == {"course": "Distributed Systems", "goal": "Build a lab"}


def test_malformed_profile_update_proposal_is_removed_without_being_applied() -> None:
    response, changes = extract_profile_update(
        'Please confirm. <profile_update>{not-json}</profile_update>'
    )

    assert response == "Please confirm."
    assert changes is None

