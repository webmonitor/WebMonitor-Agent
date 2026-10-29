"""Server-derived identity and ownership checks."""
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from webmonitor.errors import DomainError


@dataclass(frozen=True)
class CurrentUser:
    user_id: UUID
    role: Literal["admin", "member"] = "member"


class Owned(Protocol):
    user_id: UUID


def is_admin(user: CurrentUser) -> bool:
    return user.role == "admin"


def require_admin(user: CurrentUser) -> None:
    if not is_admin(user):
        raise DomainError("forbidden", 403)


def require_owner(user: CurrentUser, resource: Owned | None) -> Owned:
    """Hide other users' rows from members; administrators may operate on any row."""
    if resource is None:
        raise DomainError("not_found", 404)
    if resource.user_id != user.user_id and not is_admin(user):
        raise DomainError("forbidden", 403)
    return resource
