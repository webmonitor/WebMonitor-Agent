"""One failure shape shared by every delivery transport.

The code, message and retryability are stored on the delivery row; server text is
never copied into them because it can echo credentials or message content.
"""
from dataclasses import dataclass


@dataclass
class DeliveryFailure(Exception):
    code: str
    message: str
    retryable: bool = False
    response_code: int | None = None
