import pytest

from study_agent.github import repository_summary


def test_rejects_invalid_repository_name() -> None:
    with pytest.raises(ValueError, match="owner/repo"):
        repository_summary("https://github.com/owner/repo")

