"""Model-written email designs: a proposal the user reviews, never a direct write.

The model returns one JSON object; this module validates it into the same
`EmailTemplateConfig` the renderer uses and rejects blocks that name a specific
field, so a generated design fits any monitor.
"""
import json
import logging

from pydantic import BaseModel, Field, ValidationError

from webmonitor.errors import DomainError
from webmonitor.schemas.templates import EmailTemplateConfig, template_fields

logger = logging.getLogger(__name__)

PROMPT_LIMIT = 1000
EVENTS = ("content_changed", "list_changed", "run_failed", "recovered")
BLOCK_GUIDE = (
    '{"type":"text","text":"<sentence, <=500 chars>"}\n'
    '{"type":"summary"}\n'
    '{"type":"all_fields"}\n'
    '{"type":"event_time"}\n'
    '{"type":"monitor_link"}\n'
    '{"type":"evidence_link"}\n'
    '{"type":"divider"}'
)

INSTRUCTIONS = """You design the look of a notification email for a monitor that watches public web pages.

Reply with one JSON object, nothing else:
{{"name": "<one line, <=200 chars, names the design>", "config": {{
  "subject": "...",
  "style": {{
    "page_background": "#rrggbb", "surface": "#rrggbb", "text": "#rrggbb",
    "muted": "#rrggbb", "accent": "#rrggbb",
    "font": "sans|serif|mono", "heading_scale": "compact|regular|large",
    "density": "tight|regular|roomy", "radius": <0-24>,
    "border": true|false, "uppercase_labels": true|false
  }},
  "intros": {{"<event>": "..."}},
  "blocks": [...]
}}}}

Blocks, in the order they should appear (1 to 12 items). Use only these shapes:
{blocks}

Rules:
- style carries the whole visual design: five 6-digit hex colours, one font family,
  one heading scale, one density, a corner radius, whether the card has a border, and
  whether small labels are uppercase. The server turns these tokens into the email CSS,
  so never write CSS or HTML anywhere.
- Honour the description literally when it names a colour, a font, a density, a corner
  or a label style: translate those words into the matching tokens instead of choosing
  your own. Only fill what the description leaves open.
- text must stay clearly readable on surface, and muted must stay readable but quieter.
- subject: <=200 characters, one line. Allowed placeholders: {{monitor_name}}, {{event_label}}, {{event_date}}. No other braces.
- intros: optional; keys may only be {events}; each value <=500 characters. Leave a key out to send no intro for that event.
- Never name a specific field: no block may reference a field such as a price, a title or a status. The design must fit any monitor, and "all_fields" already lists whatever it collects.
- Write name, subject and intros in the language of the description below. Keep it plain and factual.

Description from the user:
{description}"""


class Proposal(BaseModel):
    """What the model must return: a name and a design."""

    name: str = Field(min_length=1, max_length=200)
    config: EmailTemplateConfig


def _prompt(description: str) -> str:
    return INSTRUCTIONS.format(blocks=BLOCK_GUIDE, events=", ".join(EVENTS),
                               description=description.strip()[:PROMPT_LIMIT])


def _reply_text(response) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    return str(getattr(message, "content", "") or "")


def _parse(raw: str) -> Proposal:
    """A JSON object, possibly wrapped in a code fence by the provider."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        _, _, text = text.partition("\n")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("reply is not a JSON object")
    return Proposal.model_validate(json.loads(text[start:end + 1]))


def _luminance(color: str) -> float:
    channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(foreground: str, background: str) -> float:
    a, b = _luminance(foreground), _luminance(background)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def _unreadable(proposal: Proposal) -> list[str]:
    """A design nobody can read is not a design."""
    style = proposal.config.style
    problems = []
    if _contrast(style.text, style.surface) < 3:
        problems.append("style.text has too little contrast on style.surface")
    if _contrast(style.muted, style.surface) < 2:
        problems.append("style.muted has too little contrast on style.surface")
    if _contrast(style.accent, style.surface) < 2:
        problems.append("style.accent has too little contrast on style.surface")
    return problems


def _unsupported(proposal: Proposal) -> list[str]:
    """Blocks that would tie the design to one monitor's field names."""
    problems = _unreadable(proposal)
    problems += [f"block {index} type {block.type} is not allowed"
                for index, block in enumerate(proposal.config.blocks)
                if block.type in ("field", "list_changes")]
    if template_fields(proposal.config):
        problems.append("blocks must not name specific fields")
    return problems


async def draft_template(description: str, *, client, model: str) -> Proposal:
    """One proposal, with a single repair attempt when validation fails."""
    description = description.strip()
    if not description:
        raise DomainError("validation_failed", 422)
    messages = [
        {"role": "system", "content": _prompt(description)},
        {"role": "user", "content": description},
    ]
    problems: list[str] = []
    reply = ""
    for attempt in range(2):
        response = await client.chat.completions.create(
            model=model, messages=messages, temperature=0.4, max_tokens=1200)
        reply = _reply_text(response)
        try:
            proposal = _parse(reply)
            problems = _unsupported(proposal)
            if not problems:
                return proposal
        except (ValidationError, ValueError) as exc:
            problems = [str(exc)[:300]]
        if attempt == 0:
            # Tell the model exactly what failed; it never gets a second free guess.
            messages = [*messages,
                        {"role": "assistant", "content": reply},
                        {"role": "user", "content":
                            "That design is invalid: " + "; ".join(problems[:5])
                            + ". Reply with the corrected JSON object only."}]
    logger.info("Template generation failed validation: %s", problems[:3])
    raise DomainError("template_generation_failed", 502,
                      details={"errors": problems[:5]})
