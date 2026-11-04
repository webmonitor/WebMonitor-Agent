"""User-owned delivery settings, versioned separately from the collection contract."""
from uuid import UUID

from pydantic import Field, model_validator

from webmonitor.schemas.monitors import Schedule
from webmonitor.schemas.notifications import Contract


class DeliverySettings(Contract):
    """Who is told, how often, and in which mail design.

    A draft may carry empty settings; publication requires at least one group and a
    schedule. `email_template_id=None` means the packaged default template.
    """

    notification_group_ids: list[UUID] = Field(default_factory=list)
    schedule: Schedule | None = None
    email_template_id: UUID | None = None

    @model_validator(mode='after')
    def unique_groups(self) -> 'DeliverySettings':
        if len(set(self.notification_group_ids)) != len(self.notification_group_ids):
            raise ValueError('duplicate notification group')
        return self
