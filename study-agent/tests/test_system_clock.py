from datetime import datetime

from study_agent.system_clock import system_time


def test_system_time_is_timezone_aware() -> None:
    payload = system_time()
    parsed = datetime.fromisoformat(payload["iso"])
    assert parsed.tzinfo is not None
    assert payload["date"] == parsed.date().isoformat()
    assert payload["utc_offset"]
