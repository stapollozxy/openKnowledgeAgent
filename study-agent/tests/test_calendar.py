from datetime import datetime

from study_agent import calendar


def test_create_event_passes_local_components(monkeypatch) -> None:
    captured = []
    monkeypatch.setattr(calendar, "_run", lambda command: captured.extend(command) or "")

    calendar.create_event(
        "test-event",
        datetime(2026, 11, 7, 19, 30),
        45,
        "test-calendar",
    )

    assert captured[-8:] == [
        "test-event",
        "2026",
        "11",
        "7",
        "19",
        "30",
        "45",
        "test-calendar",
    ]

