from __future__ import annotations

import json
import subprocess
from datetime import datetime
from typing import Any


LIST_SCRIPT = r'''
ObjC.import('EventKit');
ObjC.import('Foundation');
function run(argv) {
  const days = Number(argv[0]);
  const store = $.EKEventStore.alloc.init;
  const start = $.NSDate.date;
  const end = $.NSDate.dateWithTimeIntervalSinceNow(days * 86400);
  const pred = store.predicateForEventsWithStartDateEndDateCalendars(start, end, null);
  const events = store.eventsMatchingPredicate(pred).js;
  return JSON.stringify(events.map(e => ({
    title: e.title.js,
    start: e.startDate.descriptionWithLocale(null).js,
    end: e.endDate.descriptionWithLocale(null).js,
    calendar: e.calendar.title.js
  })));
}
'''


CREATE_SCRIPT = r'''
on run argv
    set eventTitle to item 1 of argv
    set startYear to (item 2 of argv) as integer
    set startMonth to (item 3 of argv) as integer
    set startDay to (item 4 of argv) as integer
    set startHour to (item 5 of argv) as integer
    set startMinute to (item 6 of argv) as integer
    set durationMinutes to (item 7 of argv) as integer
    set calendarName to item 8 of argv
    set startDate to current date
    set year of startDate to startYear
    set month of startDate to startMonth
    set day of startDate to startDay
    set time of startDate to (startHour * 3600 + startMinute * 60)
    set endDate to startDate + durationMinutes * 60
    tell application "Calendar"
        tell calendar calendarName
            make new event with properties {summary:eventTitle, start date:startDate, end date:endDate}
        end tell
    end tell
end run
'''


def _run(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Calendar command failed")
    return result.stdout.strip()


def list_events(days: int = 7) -> list[dict[str, Any]]:
    if days < 1 or days > 30:
        raise ValueError("days must be between 1 and 30")
    output = _run(["osascript", "-l", "JavaScript", "-e", LIST_SCRIPT, str(days)])
    return json.loads(output or "[]")


def create_event(
    title: str,
    start: datetime,
    duration_minutes: int,
    calendar_name: str,
) -> None:
    if duration_minutes <= 0:
        raise ValueError("duration_minutes must be positive")
    _run(
        [
            "osascript",
            "-e",
            CREATE_SCRIPT,
            "--",
            title,
            str(start.year),
            str(start.month),
            str(start.day),
            str(start.hour),
            str(start.minute),
            str(duration_minutes),
            calendar_name,
        ]
    )

