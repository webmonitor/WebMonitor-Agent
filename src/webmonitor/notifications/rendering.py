"""Packaged server-owned templates, or a validated structured user design."""
import re

import nh3
from jinja2 import Environment, PackageLoader, StrictUndefined, TemplateError

from webmonitor.errors import DomainError
from webmonitor.notifications.format import host, readable, utc_datetime
from webmonitor.schemas.notifications import EVENT_TYPES, NotificationPayload
from webmonitor.schemas.templates import EmailTemplateConfig

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

EVENT_LABELS = {
    "list_changed": "列表变化",
    "content_changed": "内容变化",
    "run_failed": "采集失败",
    "recovered": "采集已恢复",
}

for _environment in (_html, _text):
    _environment.filters["readable"] = readable
    _environment.filters["utc_datetime"] = utc_datetime
    _environment.filters["host"] = host


def render_email(event_type: str, payload: dict,
                 template: EmailTemplateConfig | None = None) -> dict:
    """A packaged template, or the user's stored structured design."""
    if event_type not in EVENT_TYPES:
        raise DomainError("template_unavailable", 409)
    data = NotificationPayload.model_validate(payload).model_dump(mode="json")
    if template is not None:
        from webmonitor.notifications.custom import render_custom_email
        return render_custom_email(event_type, data, template)
    try:
        context = {**data, "event_label": EVENT_LABELS[event_type]}
        html = _html.get_template(f"{event_type}.html").render(**context)
        plain = _text.get_template(f"{event_type}.txt").render(**context)
        plain = re.sub(r"\n{3,}", "\n\n", plain).strip() + "\n"
    except (TemplateError,TypeError,ValueError):
        raise DomainError("template_contract_failed",422) from None
    subject = f"{data['monitor']['name']}：{EVENT_LABELS[event_type]}".replace("\r", " ").replace("\n", " ")
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
_BODY_STYLE = re.compile(r'<body[^>]*\bstyle="([^"]*)"', re.IGNORECASE)


def _preview_body_style(html: str) -> str:
    """A design's own paper and type, limited to properties a preview may use."""
    match = _BODY_STYLE.search(html)
    if match is None:
        return _PREVIEW_BODY_STYLE
    kept = []
    for declaration in match.group(1).split(";"):
        name, _, value = declaration.partition(":")
        name, value = name.strip().lower(), value.strip()
        if name in _PREVIEW_STYLE_PROPERTIES and value and "url(" not in value.lower():
            kept.append(f"{name}:{value}")
    return ";".join(kept) or _PREVIEW_BODY_STYLE


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
        f'</head><body style="{_preview_body_style(html)}">{content}</body></html>'
    )
