from __future__ import annotations

from datetime import datetime
from typing import Any


def system_time() -> dict[str, Any]:
    """Return the Mac's current local time with an explicit UTC offset."""
    current = datetime.now().astimezone()
    return {
        "iso": current.isoformat(timespec="seconds"),
        "date": current.date().isoformat(),
        "time": current.time().isoformat(timespec="seconds"),
        "timezone": current.tzname(),
        "utc_offset": current.strftime("%z"),
        "unix_timestamp": int(current.timestamp()),
    }
