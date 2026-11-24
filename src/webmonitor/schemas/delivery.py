"""User-owned delivery settings, versioned separately from the collection contract."""
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from webmonitor.schemas.monitors import Schedule
from webmonitor.schemas.notifications import Contract, EventType

DeliveryChannel = Literal['email', 'webhook', 'both']
RouteChannel = Literal['email', 'webhook']


class QuietHours(Contract):
    start: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    end: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')

    @model_validator(mode='after')
    def nonempty_window(self) -> 'QuietHours':
        if self.start == self.end:
            raise ValueError('quiet hours start and end must differ')
        return self


class DeliverySettings(Contract):
    """Who is told, how often, and through which channel.

    A draft may carry empty settings; publication requires a schedule and the
    configuration of the selected channel. `channel` selects exactly one route:
    notification groups and the mail template for email, or the webhook URL.
    `email_template_id=None` means the packaged default template.
    """

    channel: DeliveryChannel = 'email'
    event_channels: dict[EventType, RouteChannel] = Field(default_factory=dict)
    notification_group_ids: list[UUID] = Field(default_factory=list)
    webhook_url: str | None = Field(default=None, max_length=1000)
    schedule: Schedule | None = None
    email_template_id: UUID | None = None
    notification_cooldown_seconds: int = Field(default=0, ge=0, le=2_147_483_647, strict=True)
    quiet_hours: QuietHours | None = None

    @field_validator('webhook_url')
    @classmethod
    def trimmed_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode='after')
    def channel_contract(self) -> 'DeliverySettings':
        if len(set(self.notification_group_ids)) != len(self.notification_group_ids):
            raise ValueError('duplicate notification group')
        if self.channel in ('webhook', 'both') and self.webhook_url is None:
            raise ValueError('webhook/both channel requires a webhook URL')
        return self
