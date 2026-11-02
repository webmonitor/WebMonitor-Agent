"""Only packaged server-owned templates are evaluated, never user template code."""
import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import nh3
from jinja2 import Environment, PackageLoader, StrictUndefined, TemplateError

from webmonitor.errors import DomainError
from webmonitor.schemas.notifications import EVENT_TYPES, NotificationPayload

_html = Environment(
    loader=PackageLoader("webmonitor.notifications", "templates"),
    undefined=StrictUndefined,
    autoescape=True,
)
_text = Environment(
    loader=PackageLoader("webmonitor.notifications", "templates"),
    undefined=StrictUndefined,
    autoescape=False,
)

_SUBJECTS = {
    "price_changed": "价格变化",
    "list_changed": "列表变化",
    "content_changed": "内容变化",
    "run_failed": "采集失败",
    "recovered": "采集已恢复",
}

_CURRENCIES = {"CNY": "¥", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


def _readable(value, timezone_name: str = "UTC") -> str:
    """Read a stored value the way the dashboard does: money, dates, lists."""
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, dict):
        if "amount" in value and "currency" in value:
            symbol = _CURRENCIES.get(str(value["currency"]))
            return f"{symbol}{value['amount']}" if symbol else f"{value['currency']} {value['amount']}"
        return "，".join(
            f"{key}: {_readable(item, timezone_name)}" for key, item in value.items()
        )
    if isinstance(value, list):
        return "、".join(_readable(item, timezone_name) for item in value)
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


def _utc_datetime(value) -> str:
    """The event time is always presented in UTC, as the mail says it is."""
    if not value:
        return "—"
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _host(value) -> str:
    try:
        return urlparse(str(value)).netloc or str(value)
    except ValueError:
        return str(value)


for _environment in (_html, _text):
    _environment.filters["readable"] = _readable
    _environment.filters["utc_datetime"] = _utc_datetime
    _environment.filters["host"] = _host


def render_email(event_type: str, payload: dict) -> dict:
    """Only the packaged template for this event type is ever evaluated."""
    if event_type not in EVENT_TYPES:
        raise DomainError("template_unavailable", 409)
    data = NotificationPayload.model_validate(payload).model_dump(mode="json")
    if event_type == "price_changed" and "current_price" not in data["fields"]:
        raise DomainError("template_contract_failed",422,"Price template requires current_price")
    try:
        context = {**data, "event_label": _SUBJECTS[event_type]}
        html = _html.get_template(f"{event_type}.html").render(**context)
        plain = _text.get_template(f"{event_type}.txt").render(**context)
        plain = re.sub(r"\n{3,}", "\n\n", plain).strip() + "\n"
    except (TemplateError,TypeError,ValueError):
        raise DomainError("template_contract_failed",422) from None
    subject = f"{data['monitor']['name']}：{_SUBJECTS[event_type]}".replace("\r", " ").replace("\n", " ")
    return {"subject": subject, "html": html, "text": plain}


# Inline CSS is what makes a sent email readable; the preview keeps the same
# appearance while still dropping positioning, scripts and external URLs.
_PREVIEW_STYLE_PROPERTIES = {
    "background", "background-color", "border", "border-bottom", "border-top",
    "border-radius", "box-sizing", "color", "display", "font-family", "font-size",
    "font-weight", "height", "letter-spacing", "line-height", "margin", "margin-bottom",
    "margin-top", "max-width", "overflow-wrap", "padding", "padding-bottom",
    "padding-top", "text-align", "text-decoration", "white-space", "width",
}


_PREVIEW_BODY_STYLE = (
    "margin:0;padding:24px;background:#f5f2ea;color:#1e1b16;"
    "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;"
    "font-size:15px;line-height:1.6"
)


def sanitize_preview(html: str) -> str:
    clean = nh3.clean(
        html,
        tags={"html","head","body","title","meta","h1","h2","h3","p","a","strong","em","table","thead","tbody","tr","th","td","ul","ol","li","br","pre","code","div","span","hr","main"},
        attributes={"*":{"style"},"a":{"href","title"}},
        filter_style_properties=_PREVIEW_STYLE_PROPERTIES,
        url_schemes={"http","https"},
        link_rel="noopener noreferrer",
    )
    # nh3 drops attributes from <body> and the app renders the preview in an
    # iframe, so the mail's own paper and type are applied to the wrapper.
    inner = re.search(r"<body[^>]*>(.*)</body>", clean, re.S)
    content = inner.group(1) if inner else clean
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
        f'</head><body style="{_PREVIEW_BODY_STYLE}">{content}</body></html>'
    )
