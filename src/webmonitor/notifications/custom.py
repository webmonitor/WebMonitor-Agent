"""Render a stored structured template design: the app owns layout and escaping.

A user template is data, never code. Every value read from the payload is escaped
here, block order is the stored order, and the style tokens only feed the CSS the
server writes, so a design can restyle the mail without carrying markup.
"""
from html import escape
from typing import Any

from webmonitor.notifications.format import host, readable, utc_datetime
from webmonitor.notifications.rendering import EVENT_LABELS, sanitize_preview
from webmonitor.schemas.notifications import EVENT_TYPES, NotificationPayload
from webmonitor.schemas.templates import (
    SUBJECT_TOKEN,
    AllFieldsBlock,
    DividerBlock,
    EmailTemplateConfig,
    EventTimeBlock,
    EvidenceLinkBlock,
    FieldBlock,
    ListChangesBlock,
    MonitorLinkBlock,
    SummaryBlock,
    TemplateStyle,
    TextBlock,
)

EMPTY = "—"
MORE_TEMPLATE = "另有 {count} 项"

_FONTS = {
    "sans": ("-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',"
             "'Microsoft YaHei',sans-serif"),
    "serif": "Georgia,'Times New Roman','Songti SC','SimSun',serif",
    "mono": "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,monospace",
}
_SCALES = {
    "compact": {"heading": "19px", "intro": "13px", "body": "13px",
                "label": "11px", "emphasis": "21px"},
    "regular": {"heading": "22px", "intro": "15px", "body": "15px",
                "label": "12px", "emphasis": "24px"},
    "large": {"heading": "26px", "intro": "16px", "body": "16px",
              "label": "13px", "emphasis": "28px"},
}
_DENSITY = {
    "tight": {"page_pad": "12px", "card_pad": "18px", "block": "8px", "gap": "2px"},
    "regular": {"page_pad": "24px", "card_pad": "32px", "block": "14px", "gap": "4px"},
    "roomy": {"page_pad": "32px", "card_pad": "40px", "block": "20px", "gap": "6px"},
}
_WIDTH = "620px"
_SHELL_PADDING = "9px 16px"


class Look:
    """Every CSS value a block may use, derived from the design's style tokens."""

    def __init__(self, style: TemplateStyle):
        scale, density = _SCALES[style.heading_scale], _DENSITY[style.density]
        self.font = _FONTS[style.font]
        self.page_pad = density["page_pad"]
        self.card_pad = density["card_pad"]
        self.block = density["block"]
        self.gap = density["gap"]
        self.heading = scale["heading"]
        self.intro = scale["intro"]
        self.body = scale["body"]
        self.label = scale["label"]
        self.emphasis = scale["emphasis"]
        self.page = style.page_background
        self.surface = style.surface
        self.text = style.text
        self.muted = style.muted
        self.accent = style.accent
        self.rule = self._tint(style.text)
        self.radius = f"{style.radius}px" if style.border else "0"
        self.card_border = f"1px solid {self.rule}" if style.border else "0"
        self.uppercase = ("text-transform:uppercase;letter-spacing:0.04em;"
                          if style.uppercase_labels else "")

    @staticmethod
    def _tint(color: str) -> str:
        """A hairline from the text colour, so one palette controls the rules too."""
        return f"{color}26"

    def label_style(self) -> str:
        return (f"margin:{self.block} 0 0;color:{self.muted};"
                f"font-size:{self.label};{self.uppercase}")

    def body_style(self) -> str:
        return f"font-size:{self.body};line-height:1.65"

    def value_style(self) -> str:
        return f"font-size:{self.body}"


def _money(value) -> str:
    return readable(value) if value not in (None, "") else EMPTY


def _label(payload: dict, name: str, override: str | None = None) -> str:
    if override:
        return override
    return (payload["change"].get("labels") or {}).get(name, name)


def _current(payload: dict, name: str):
    return (payload["fields"] or {}).get(name)


def _before(payload: dict, name: str):
    return (payload["change"].get("before") or {}).get(name)


def _row_text(row: dict, labels: dict, timezone_name: str) -> str:
    headline = row.get("title") or row.get("name") or row.get("label")
    parts = [readable(headline, timezone_name)] if headline else []
    for key, value in row.items():
        if key in ("title", "name", "label"):
            continue
        parts.append(f"{labels.get(key, key)} {readable(value, timezone_name)}")
    return " · ".join(part for part in parts if part) or EMPTY


def _change_rows(payload: dict, block: ListChangesBlock) -> list[str]:
    """Every changed row this event carried for the block's list field."""
    labels = payload["change"].get("labels") or {}
    timezone_name = payload["monitor"].get("timezone") or "UTC"
    rows: list[str] = []
    for difference in payload["change"].get("differences") or []:
        if difference.get("field") != block.field:
            continue
        kind = difference.get("type")
        for item in difference.get("items") or []:
            if kind == "list_updated":
                names = item.get("fields") or []
                before, after = item.get("before") or {}, item.get("after") or {}
                rows.append("；".join(
                    f"{labels.get(name, name)}：{readable(before.get(name), timezone_name)}"
                    f" → {readable(after.get(name), timezone_name)}" for name in names))
            elif kind in ("list_added", "list_removed"):
                marker = "+" if kind == "list_added" else "−"
                rows.append(f"{marker} {_row_text(item, labels, timezone_name)}")
    return rows


def _subject(config: EmailTemplateConfig, event_type: str, payload: dict) -> str:
    values = {
        "monitor_name": payload["monitor"]["name"],
        "event_label": EVENT_LABELS[event_type],
        "event_date": utc_datetime(payload["event"]["detected_at"]),
    }
    subject = SUBJECT_TOKEN.sub(lambda match: values[match.group(1)], config.subject)
    return subject.replace("\r", " ").replace("\n", " ").strip()


def _blocks_html(config: EmailTemplateConfig, payload: dict) -> list[str]:
    look = Look(config.style)
    out: list[str] = []
    for block in config.blocks:
        if isinstance(block, TextBlock):
            out.append(f'<p style="margin:{look.block} 0 0;{look.value_style()}">'
                       f'{escape(block.text)}</p>')
        elif isinstance(block, SummaryBlock):
            summary = payload["change"].get("summary") or ""
            if summary:
                out.append(f'<p style="margin:{look.block} 0 0;{look.value_style()}">'
                           f'{escape(summary)}</p>')
        elif isinstance(block, FieldBlock):
            values = []
            if block.show in ("before", "both"):
                values.append(_money(_before(payload, block.field)))
            if block.show in ("current", "both"):
                values.append(_money(_current(payload, block.field)))
            label = _label(payload, block.field, block.label)
            size = look.emphasis if block.emphasis else look.body
            body = " → ".join(escape(value) for value in values if value)
            out.append(
                f'<p style="{look.label_style()}">{escape(label)}</p>'
                f'<p style="margin:2px 0 0;color:{look.accent};font-size:{size};'
                f'line-height:1.2;font-weight:600">{body or EMPTY}</p>')
        elif isinstance(block, AllFieldsBlock):
            names = block.fields or list((payload["fields"] or {}).keys())
            cells = "".join(
                f'<p style="margin:{look.block} 0 0;{look.value_style()}">'
                f'<span style="color:{look.muted};font-size:{look.label}">'
                f'{escape(_label(payload, name))}</span><br>'
                f'{escape(_money(_current(payload, name)))}</p>'
                for name in names)
            out.append(f'<div style="margin:{look.block} 0 0">{cells}</div>')
        elif isinstance(block, ListChangesBlock):
            rows = _change_rows(payload, block)
            shown, hidden = rows[:block.limit], max(0, len(rows) - block.limit)
            items = "".join(f'<li style="margin:{look.gap} 0 0">{escape(row)}</li>'
                            for row in shown)
            more = (f'<p style="margin:6px 0 0;color:{look.muted};'
                    f'font-size:{look.label}">{MORE_TEMPLATE.format(count=hidden)}</p>'
                    if hidden else "")
            if items or more:
                out.append(
                    f'<p style="{look.label_style()}">'
                    f'{escape(_label(payload, block.field))}</p>'
                    f'<ul style="margin:6px 0 0;padding-left:18px;{look.value_style()}">'
                    f'{items}</ul>{more}')
        elif isinstance(block, EventTimeBlock):
            out.append(f'<p style="{look.label_style()}">检测时间（UTC）：'
                       f'<span style="color:{look.accent}">'
                       f'{escape(utc_datetime(payload["event"]["detected_at"]))}</span></p>')
        elif isinstance(block, MonitorLinkBlock):
            url = payload["monitor"]["url"]
            out.append(f'<p style="margin:{look.block} 0 0;font-size:{look.intro}">'
                       f'监控页面：<a href="{escape(url, quote=True)}" '
                       f'style="color:{look.accent}">{escape(host(url))}</a></p>')
        elif isinstance(block, EvidenceLinkBlock):
            url = payload.get("evidence_url") or ""
            if url:
                out.append(
                    f'<p style="margin:{look.block} 0 0">'
                    f'<a href="{escape(url, quote=True)}" '
                    f'style="display:inline-block;padding:{_SHELL_PADDING};'
                    f'background:{look.accent};color:{look.surface};'
                    f'border-radius:{look.radius};text-decoration:none;'
                    f'font-size:{look.intro};font-weight:600">查看完整记录</a></p>')
        elif isinstance(block, DividerBlock):
            out.append(f'<hr style="border:0;border-top:1px solid {look.rule};'
                       f'margin:{look.block} 0">')
    return out


def _blocks_text(config: EmailTemplateConfig, payload: dict) -> list[str]:
    out: list[str] = []
    for block in config.blocks:
        if isinstance(block, TextBlock):
            out.append(block.text)
        elif isinstance(block, SummaryBlock):
            summary = payload["change"].get("summary") or ""
            if summary:
                out.append(summary)
        elif isinstance(block, FieldBlock):
            values = []
            if block.show in ("before", "both"):
                values.append(_money(_before(payload, block.field)))
            if block.show in ("current", "both"):
                values.append(_money(_current(payload, block.field)))
            out.append(f'{_label(payload, block.field, block.label)}：'
                       f'{" → ".join(values) or EMPTY}')
        elif isinstance(block, AllFieldsBlock):
            names = block.fields or list((payload["fields"] or {}).keys())
            out.extend(f'{_label(payload, name)}：{_money(_current(payload, name))}'
                       for name in names)
        elif isinstance(block, ListChangesBlock):
            rows = _change_rows(payload, block)
            if rows:
                out.append(_label(payload, block.field))
                out.extend(f'  {row}' for row in rows[:block.limit])
                if len(rows) > block.limit:
                    out.append(f'  {MORE_TEMPLATE.format(count=len(rows) - block.limit)}')
        elif isinstance(block, EventTimeBlock):
            out.append(f'检测时间（UTC）：{utc_datetime(payload["event"]["detected_at"])}')
        elif isinstance(block, MonitorLinkBlock):
            out.append(f'监控页面：{payload["monitor"]["url"]}')
        elif isinstance(block, EvidenceLinkBlock):
            url = payload.get("evidence_url") or ""
            if url:
                out.append(f'查看完整记录：{url}')
        elif isinstance(block, DividerBlock):
            out.append("---")
    return out


def _shell_html(config: EmailTemplateConfig, event_type: str, payload: dict,
                blocks: list[str]) -> str:
    look = Look(config.style)
    intro = config.intros.get(event_type, "")
    intro_html = (f'<p style="margin:{look.block} 0 0;font-size:{look.intro}">'
                  f'{escape(intro)}</p>' if intro else "")
    body = "\n".join(blocks)
    card = (f'max-width:{_WIDTH};margin:0 auto;padding:{look.card_pad};'
            f'background:{look.surface};border:{look.card_border};'
            f'border-radius:{look.radius}')
    return (
        f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{escape(payload["monitor"]["name"])} · '
        f'{escape(EVENT_LABELS[event_type])}</title></head>'
        f'<body style="margin:0;padding:{look.page_pad};background:{look.page};'
        f'color:{look.text};font-family:{look.font};{look.body_style()}">'
        f'<main style="{card}">'
        f'<p style="margin:0;color:{look.accent};font-size:{look.label};'
        f'font-weight:600;{look.uppercase}">WebMonitor</p>'
        f'<h1 style="margin:10px 0 0;font-size:{look.heading};line-height:1.3;'
        f'font-weight:600">{escape(payload["monitor"]["name"])}</h1>'
        f'<p style="margin:6px 0 0;color:{look.muted};font-size:{look.label}">'
        f'{escape(EVENT_LABELS[event_type])}</p>'
        f'{intro_html}{body}'
        f'<hr style="border:0;border-top:1px solid {look.rule};margin:24px 0 12px">'
        f'<p style="margin:0;color:{look.muted};font-size:{look.label};line-height:1.6;'
        f'overflow-wrap:anywhere">监控 ID：{escape(str(payload["monitor"]["id"]))}<br>'
        f'事件 ID：{escape(str(payload["event"]["id"]))}<br>'
        f'事件类型：{escape(payload["event"]["type"])}</p>'
        '</main></body></html>'
    )


def _shell_text(config: EmailTemplateConfig, event_type: str, payload: dict,
                blocks: list[str]) -> str:
    intro = config.intros.get(event_type, "")
    lines = ["WebMonitor", "", payload["monitor"]["name"], EVENT_LABELS[event_type]]
    if intro:
        lines += ["", intro]
    if blocks:
        lines += [""] + blocks
    lines += ["", "---",
              f'监控 ID：{payload["monitor"]["id"]}',
              f'事件 ID：{payload["event"]["id"]}',
              f'事件类型：{payload["event"]["type"]}']
    return "\n".join(lines) + "\n"


def render_custom_email(event_type: str, payload: dict,
                        config: EmailTemplateConfig) -> dict:
    """Render one stored design for one event type."""
    data = NotificationPayload.model_validate(payload).model_dump(mode="json")
    return {
        "subject": _subject(config, event_type, data),
        "html": _shell_html(config, event_type, data,
                            _blocks_html(config, data)),
        "text": _shell_text(config, event_type, data,
                            _blocks_text(config, data)),
    }


SAMPLE_TIME = "2024-05-06T02:30:00+00:00"
SAMPLE_MONITOR_ID = "00000000-0000-4000-8000-000000000001"
SAMPLE_EVENT_ID = "00000000-0000-4000-8000-000000000002"


def sample_payload() -> dict:
    """Deterministic data for the template management preview: a generic page."""
    labels = {"page_title": "页面标题", "notice": "公告列表", "title": "标题",
              "state": "状态"}
    current = {
        "page_title": "示例页面 · 学期公告",
        "notice": [{"title": "秋季学期注册通知", "state": "进行中"},
                   {"title": "选课截止日期", "state": "已发布"}],
    }
    before = {
        "page_title": "示例页面 · 学期安排",
        "notice": [{"title": "秋季学期注册通知", "state": "待发布"},
                   {"title": "选课截止日期", "state": "已发布"}],
    }
    payload: dict[str, Any] = {
        "monitor": {"id": SAMPLE_MONITOR_ID, "name": "示例监控：公告页",
                    "url": "https://example.com/notices", "timezone": "Asia/Shanghai"},
        "event": {"id": SAMPLE_EVENT_ID, "type": "content_changed",
                  "detected_at": SAMPLE_TIME},
        "change": {"before": before, "after": current,
                   "summary": "页面标题与公告状态发生更新",
                   "differences": [
                       {"rule_index": 0, "type": "text_changed",
                        "field": "page_title", "before": before["page_title"],
                        "after": current["page_title"]},
                       {"rule_index": 1, "type": "list_updated", "field": "notice",
                        "before": before["notice"], "after": current["notice"],
                        "items": [{"before": before["notice"][0], "after": current["notice"][0],
                                   "fields": ["state"]}]},
                   ],
                   "labels": labels},
        "fields": current,
        "evidence_url": "https://webmonitor.example/app/monitors/"
                        + SAMPLE_MONITOR_ID,
    }
    return payload


def preview_template(config: EmailTemplateConfig) -> list[dict]:
    """Every event type rendered with the same sample, for the management page."""
    payload = sample_payload()
    rendered = []
    for event_type in sorted(EVENT_TYPES):
        message = render_custom_email(event_type, {**payload, "event": {
            **payload["event"], "type": event_type}}, config)
        rendered.append({"event_type": event_type, "subject": message["subject"],
                         "html": message["html"], "text": message["text"],
                         "preview_html": sanitize_preview(message["html"])})
    return rendered
