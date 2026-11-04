"""Structured, user-authored email templates: blocks, never template code."""
import re
from typing import Annotated, Literal

from pydantic import Field, StrictBool, field_validator

from webmonitor.schemas.monitors import MonitorSpec
from webmonitor.schemas.notifications import EVENT_TYPES, Contract

SUBJECT_TOKENS = frozenset({'monitor_name', 'event_label', 'event_date'})
# Every style value is a bounded token: the renderer builds the CSS from it, so a
# design can restyle the mail without ever carrying markup or a style string.
HEX_COLOR = r'^#[0-9a-fA-F]{6}$'


class TemplateStyle(Contract):
    """The look of one design; the server owns which CSS property uses which value."""

    page_background: str = Field(default='#f5f2ea', pattern=HEX_COLOR)
    surface: str = Field(default='#fffdf8', pattern=HEX_COLOR)
    text: str = Field(default='#1e1b16', pattern=HEX_COLOR)
    muted: str = Field(default='#6f6759', pattern=HEX_COLOR)
    accent: str = Field(default='#22584a', pattern=HEX_COLOR)
    font: Literal['sans', 'serif', 'mono'] = 'sans'
    heading_scale: Literal['compact', 'regular', 'large'] = 'regular'
    density: Literal['tight', 'regular', 'roomy'] = 'regular'
    radius: int = Field(default=14, ge=0, le=24, strict=True)
    border: StrictBool = True
    uppercase_labels: StrictBool = False
SUBJECT_TOKEN = re.compile(r'\{([^{}]*)\}')
MAX_BLOCKS = 12


class TextBlock(Contract):
    type: Literal['text']
    text: str = Field(min_length=1, max_length=500)


class SummaryBlock(Contract):
    type: Literal['summary']


class FieldBlock(Contract):
    type: Literal['field']
    field: str = Field(min_length=1, max_length=64)
    show: Literal['current', 'before', 'both'] = 'current'
    emphasis: bool = False
    label: str | None = Field(default=None, max_length=100)


class ListChangesBlock(Contract):
    type: Literal['list_changes']
    field: str = Field(min_length=1, max_length=64)
    limit: int = Field(default=8, ge=1, le=20, strict=True)


class AllFieldsBlock(Contract):
    type: Literal['all_fields']
    # None means every top-level field, in payload order.
    fields: list[str] | None = None


class EventTimeBlock(Contract):
    type: Literal['event_time']


class MonitorLinkBlock(Contract):
    type: Literal['monitor_link']


class EvidenceLinkBlock(Contract):
    type: Literal['evidence_link']


class DividerBlock(Contract):
    type: Literal['divider']


TemplateBlock = Annotated[TextBlock | SummaryBlock | FieldBlock | ListChangesBlock
                          | AllFieldsBlock | EventTimeBlock | MonitorLinkBlock
                          | EvidenceLinkBlock | DividerBlock, Field(discriminator='type')]

FIELD_BLOCKS = ('field', 'list_changes', 'all_fields')


class EmailTemplateConfig(Contract):
    """A stored template design; the renderer owns layout and escaping."""

    version: Literal[1] = 1
    style: TemplateStyle = Field(default_factory=TemplateStyle)
    subject: str = Field(min_length=1, max_length=200)
    intros: dict[str, str] = Field(default_factory=dict)
    blocks: list[TemplateBlock] = Field(default_factory=list, max_length=MAX_BLOCKS)

    @field_validator('subject')
    @classmethod
    def valid_subject(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('subject must not be blank')
        if '\r' in value or '\n' in value:
            raise ValueError('subject must be a single line')
        for token in SUBJECT_TOKEN.findall(value):
            if token not in SUBJECT_TOKENS:
                raise ValueError(f'{token} is not a supported subject token')
        if '{' in SUBJECT_TOKEN.sub('', value) or '}' in SUBJECT_TOKEN.sub('', value):
            raise ValueError('unbalanced subject token')
        return value

    @field_validator('intros')
    @classmethod
    def valid_intros(cls, value: dict[str, str]) -> dict[str, str]:
        for key, text in value.items():
            if key not in EVENT_TYPES:
                raise ValueError(f'{key} is not an event type')
            if len(text) > 500:
                raise ValueError('each intro is limited to 500 characters')
        return value


class TemplateIncompatible(ValueError):
    """A design that cannot be rendered against a specific collection contract."""

    def __init__(self, fields: list[str], message: str):
        super().__init__(message)
        self.fields = fields


def template_fields(config: EmailTemplateConfig) -> list[str]:
    """Every field name the design reads, in block order."""
    names: list[str] = []
    for block in config.blocks:
        if isinstance(block, (FieldBlock, ListChangesBlock)):
            names.append(block.field)
        elif isinstance(block, AllFieldsBlock) and block.fields:
            names.extend(block.fields)
    return names


def validate_template_for_spec(config: EmailTemplateConfig,
                               spec: MonitorSpec) -> None:
    """Reject a design that reads fields the collection contract does not produce."""
    fields = {field.name: field for field in spec.fields}
    missing = sorted({name for name in template_fields(config) if name not in fields})
    if missing:
        raise TemplateIncompatible(missing,
                                   'template reads unknown fields: ' + ', '.join(missing))
    business_key = spec.business_key.field if spec.business_key is not None else None
    for block in config.blocks:
        if not isinstance(block, ListChangesBlock):
            continue
        if fields[block.field].type != 'list' or block.field != business_key:
            raise TemplateIncompatible([block.field],
                f'list_changes requires the business key list field, not {block.field}')
