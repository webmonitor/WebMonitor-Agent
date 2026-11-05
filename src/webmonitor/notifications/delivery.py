"""TLS-only SMTP transport. Acceptance is not proof of inbox delivery.

A stable Message-ID helps reconciliation, but SMTP is at-least-once: acceptance
followed by a lost database commit can result in a repeated send.
"""
import asyncio
import ssl
from email.message import EmailMessage
from email.utils import format_datetime, parseaddr

import aiosmtplib
from aiosmtplib.errors import (
    SMTPConnectError,
    SMTPException,
    SMTPRecipientsRefused,
    SMTPResponseException,
    SMTPServerDisconnected,
    SMTPTimeoutError,
)

from webmonitor.config import get_settings
from webmonitor.models import utc_now
from webmonitor.notifications.errors import DeliveryFailure


def classify_smtp_failure(exc: Exception) -> DeliveryFailure:
    """Never persist server text: it may echo credentials or message content."""
    if isinstance(exc, ssl.SSLError) or isinstance(exc.__cause__, ssl.SSLError):
        return DeliveryFailure("smtp_tls_failed", "SMTP TLS validation or negotiation failed")
    if isinstance(exc, SMTPRecipientsRefused):
        codes = [recipient.code for recipient in exc.recipients]
        code = next((code for code in codes if 500 <= code < 600), codes[0] if codes else None)
        return DeliveryFailure("smtp_recipient_refused", "SMTP server refused the recipient",
                           code is not None and 400 <= code < 500, code)
    if isinstance(exc, SMTPResponseException):
        return DeliveryFailure("smtp_rejected", "SMTP server rejected the operation",
                           400 <= exc.code < 500, exc.code)
    if isinstance(exc, (SMTPConnectError, SMTPServerDisconnected, SMTPTimeoutError,
                        OSError, TimeoutError)):
        return DeliveryFailure("smtp_network_error", "SMTP connection failed or timed out", True)
    if isinstance(exc, SMTPException):
        return DeliveryFailure("smtp_protocol_error", "SMTP protocol or capability failure")
    return DeliveryFailure("smtp_configuration_error", "SMTP configuration or message is invalid")


async def send_email(delivery, rendered: dict) -> int:
    settings = get_settings()
    if settings.smtp_use_ssl == settings.smtp_starttls:
        raise DeliveryFailure("smtp_tls_configuration", "Select exactly one of SMTP SSL or STARTTLS")
    sender = parseaddr(settings.mail_from)[1]
    username = settings.smtp_username.get_secret_value()
    password = settings.smtp_password.get_secret_value()
    if (not settings.smtp_host or not sender or "@" not in sender
            or not 1 <= settings.smtp_port <= 65535 or bool(username) != bool(password)):
        raise DeliveryFailure("smtp_configuration_error", "SMTP host, sender, port or credentials are incomplete")
    smtp = None
    try:
        message = EmailMessage()
        message["From"] = settings.mail_from
        message["To"] = delivery.recipient
        message["Subject"] = rendered["subject"]
        message["Message-ID"] = delivery.message_id
        message["Date"] = format_datetime(utc_now())
        message.set_content(rendered["text"])
        message.add_alternative(rendered["html"], subtype="html")
        smtp = aiosmtplib.SMTP(
            hostname=settings.smtp_host, port=settings.smtp_port,
            username=username or None, password=password or None,
            use_tls=settings.smtp_use_ssl, start_tls=settings.smtp_starttls,
            validate_certs=True, timeout=30,
        )
        async with asyncio.timeout(30):
            await smtp.connect()
            refused, _ = await smtp.send_message(message, sender=sender, recipients=[delivery.recipient])
            if refused:
                response = next(iter(refused.values()))
                raise DeliveryFailure("smtp_recipient_refused", "SMTP server refused the recipient",
                                  400 <= response.code < 500, response.code)
        # DATA acceptance succeeded. A failure to QUIT must not turn acceptance
        # into a retry; closing the connection cannot revoke accepted mail.
        return 250
    except DeliveryFailure:
        raise
    except Exception as exc:
        raise classify_smtp_failure(exc) from None
    finally:
        if smtp is not None:
            smtp.close()
