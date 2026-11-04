"""One bounded request through the mandatory ACL egress proxy.

HTML, JSON, probe and replay all share this redirect, size and error contract;
callers decide what a status code or media type means.
"""
import asyncio
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from webmonitor.collection.decoding import BoundedDecoder
from webmonitor.config import get_settings
from webmonitor.errors import DomainError
from webmonitor.security.egress import validate_target

REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
MAX_REDIRECTS = 6


@dataclass(frozen=True)
class FetchResult:
    final_url: str
    status: int
    headers: httpx.Headers
    body: bytes


def content_type_base(headers: httpx.Headers) -> str:
    return headers.get('content-type', '').split(';', 1)[0].strip().lower()


def _charset(headers: httpx.Headers) -> str | None:
    for parameter in headers.get('content-type', '').split(';')[1:]:
        name, _, value = parameter.partition('=')
        if name.strip().lower() == 'charset':
            return value.strip().strip('"\'') or None
    return None


def decode_text(body: bytes, headers: httpx.Headers) -> str:
    for candidate in (_charset(headers), 'utf-8'):
        if not candidate:
            continue
        try:
            return body.decode(candidate, errors='replace')
        except LookupError:
            continue
    return body.decode('utf-8', errors='replace')


async def fetch_bounded(url: str, *, method: str = 'GET', headers: dict[str, str] | None = None,
                        body: bytes | None = None, accept: str, max_bytes: int,
                        transport: httpx.AsyncBaseTransport | None = None,
                        timeout: float = 30.0) -> FetchResult:
    request_headers = {'Accept': accept, 'Accept-Encoding': 'gzip, deflate'}
    if headers:
        request_headers.update(headers)
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(proxy=None if transport else get_settings().egress_proxy_url,
                                         transport=transport, trust_env=False,
                                         follow_redirects=False, timeout=timeout,
                                         headers=request_headers) as client:
                target = await validate_target(url)
                current_method, current_body = method, body
                for redirects in range(MAX_REDIRECTS):
                    async with client.stream(current_method, target, content=current_body) as response:
                        if response.status_code in REDIRECT_CODES:
                            location = response.headers.get('location')
                            if not location or redirects == MAX_REDIRECTS - 1:
                                raise DomainError('redirect_limit', 422)
                            target = await validate_target(urljoin(target, location))
                            if response.status_code in {301, 302, 303}:
                                current_method, current_body = 'GET', None
                            continue
                        if response.status_code == 403 and response.headers.get(
                                'x-squid-error', '').startswith('ERR_ACCESS_DENIED'):
                            raise DomainError('url_forbidden', 422)
                        decoder = BoundedDecoder(response.headers.get('content-encoding', 'identity'),
                                                 limit=max_bytes)
                        async for chunk in response.aiter_raw(chunk_size=65536):
                            decoder.feed(chunk)
                        return FetchResult(target, response.status_code, response.headers,
                                           decoder.finish())
                raise DomainError('redirect_limit', 422)
    except (TimeoutError, httpx.TimeoutException):
        raise DomainError('collection_timeout', 503) from None
    except httpx.ProxyError as exc:
        if str(exc).startswith('403'):
            raise DomainError('url_forbidden', 422) from None
        raise DomainError('target_unavailable', 503) from None
    except httpx.HTTPError:
        raise DomainError('target_unavailable', 503) from None
