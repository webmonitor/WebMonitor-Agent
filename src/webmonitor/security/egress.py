"""Application URL validation; actual connections MUST also use the ACL proxy."""
import ipaddress
from urllib.parse import urlsplit, urlunsplit

from webmonitor.config import allowed_target_origins, get_settings
from webmonitor.errors import DomainError


def public_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_loopback or ip.is_link_local)


def _structure(url: str):
    if not isinstance(url, str) or any(ord(c) < 33 for c in url) or "\\" in url:
        raise ValueError()
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError()
    if parsed.username is not None or parsed.password is not None:
        raise ValueError()
    _ = parsed.port  # Force malformed-port rejection.
    return parsed


def validate_url(url: str) -> str:
    settings = get_settings()
    try:
        parsed = _structure(url)
        target = urlunsplit(parsed._replace(fragment=""))
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin in allowed_target_origins() and settings.development_mode:
            return target
        if settings.target_policy == "any" and settings.development_mode:
            return target
        host = parsed.hostname.rstrip(".").casefold()
        port = parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)
        if port not in {80, 443} or "%" in host or host == "localhost" or host.endswith(".localhost") or host in {"metadata.google.internal", "metadata", "host.docker.internal"}:
            raise ValueError()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if "." not in host:
                raise ValueError("Unqualified infrastructure hostnames are not public targets")
            host.encode("idna")
        else:
            if not public_address(host):
                raise ValueError()
        return target
    except (ValueError, UnicodeError):
        raise DomainError("url_forbidden", 422, "Only public HTTP(S) targets on ports 80/443 are permitted") from None


async def validate_target(url: str) -> str:
    # Collectors have no direct Internet route or public DNS access. Resolving here
    # would fail on internal networks and introduce a second, TOCTOU-prone DNS view.
    # Squid resolves via its TLS resolver and checks each actual destination address.
    return validate_url(url)
