"""Conversation titles: a bounded placeholder, then the model's own title.

The first message names the conversation immediately so the sidebar is never
empty; the agent worker replaces that placeholder with a generated title for the
same conversation. Both paths use these helpers so the comparison is exact.
"""
import re

PROVISIONAL_LIMIT = 60
TITLE_LIMIT = 40

TITLE_PROMPT = (
    "为下面的用户请求生成一个网页监控对话的标题。标题使用用户请求的语言，"
    "不超过16个汉字或8个英文词；只输出标题本身，不要回答请求，不要解释，"
    "不要引号，不要句号。\n\n用户请求：\n{message}"
)

_QUOTES = "\"'“”‘’《》「」`*"
_PREFIX = re.compile(r"^(title|标题)\s*[:：]\s*", re.IGNORECASE)


def provisional_title(content: str) -> str | None:
    """The first message, bounded to one line, used until a title is generated."""
    line = " ".join(content.split())
    if not line:
        return None
    return line[:PROVISIONAL_LIMIT].rstrip(" ，,、。;；") + (
        "…" if len(line) > PROVISIONAL_LIMIT else ""
    )


def clean_generated_title(raw: str | None) -> str | None:
    """Remove the packaging models add around a short answer."""
    if not raw:
        return None
    line = " ".join(str(raw).split()).strip().strip(_QUOTES)
    line = _PREFIX.sub("", line).strip(_QUOTES)
    line = line.rstrip(" .。!！?？,，;；:：")
    if not line:
        return None
    return line[:TITLE_LIMIT].rstrip(" .。…") or None


def needs_generated_title(title: str | None, first_message: str) -> bool:
    """Only a missing or still-provisional title is replaced."""
    return not title or title == provisional_title(first_message)
