"""Shared value presentation for packaged and user-designed mail."""
import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


def readable(value, timezone_name: str = "UTC") -> str:
    """Read a stored value the way the dashboard does: money, dates, lists."""
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, dict):
        if "amount" in value and "currency" in value:
            # The ISO code is the whole contract; no currency is rendered specially.
            return f"{value['currency']} {value['amount']}"
        return "，".join(
            f"{key}: {readable(item, timezone_name)}" for key, item in value.items()
        )
    if isinstance(value, list):
        return "、".join(readable(item, timezone_name) for item in value)
    if isinstance(value, str):
        if _ISO_DATE.match(value):
            try:
                moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return value
            try:
                zone = ZoneInfo(timezone_name)
            except (ZoneInfoNotFoundError, ValueError):
                zone = timezone.utc
            moment = moment.astimezone(zone)
            if moment.hour == 0 and moment.minute == 0:
                return moment.strftime("%Y-%m-%d")
            return moment.strftime("%Y-%m-%d %H:%M")
        return value
    return str(value)


def utc_datetime(value) -> str:
    """The event time is always presented in UTC, as the mail says it is."""
    if not value:
        return "—"
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def host(value) -> str:
    try:
        return urlparse(str(value)).netloc or str(value)
    except ValueError:
        return str(value)
