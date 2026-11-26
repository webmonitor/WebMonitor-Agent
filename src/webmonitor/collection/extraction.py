"""Deterministic CSS extraction; missing optional values remain absent."""
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag

from webmonitor.errors import DomainError
from webmonitor.schemas.monitors import (
    MAX_LIST_ITEMS,
    FieldSpec,
    MonitorSpec,
    Normalization,
    canonical_json,
)
from webmonitor.security.egress import validate_url

# Shared symbols are interpreted only through the explicit currency contract.
_CURRENCY_SYMBOLS = {
    '$': frozenset(('USD', 'CAD', 'AUD', 'NZD', 'SGD', 'HKD', 'MXN', 'ARS', 'CLP', 'COP')),
    '€': frozenset(('EUR',)), '£': frozenset(('GBP',)),
    '¥': frozenset(('JPY', 'CNY')), '₹': frozenset(('INR',)),
    '₩': frozenset(('KRW',)), '₽': frozenset(('RUB',)),
    'US$': frozenset(('USD',)), 'R$': frozenset(('BRL',)),
    'A$': frozenset(('AUD',)), 'C$': frozenset(('CAD',)),
}
MISSING = object()
# Response limits alone do not bound the objects produced by normalization.
# These are serialized UTF-8 budgets, so non-ASCII text cannot evade them.
MAX_NORMALIZED_FIELD_BYTES = 1024 * 1024
MAX_NORMALIZED_RESULT_BYTES = 2 * 1024 * 1024


def invalid(field: str, reason: str) -> None:
    raise DomainError('collection_invalid', 422, details={'field': field, 'reason': reason})


def check_raw_list_size(field: FieldSpec, path: str, size: int) -> None:
    """Reject oversized source rows before touching any item normalization."""
    if size > MAX_LIST_ITEMS:
        raise DomainError('collection_limit', 422, details={
            'limit': 'raw_list_items', 'field': path, 'max_items': MAX_LIST_ITEMS})
    if field.max_items is not None and size > field.max_items:
        invalid(path, 'max_items')


def normalized_utf8_bytes(value: Any) -> int:
    return len(canonical_json(value).encode('utf-8'))


def _check_normalized_field_bytes(path: str, size: int) -> None:
    if size > MAX_NORMALIZED_FIELD_BYTES:
        raise DomainError('collection_limit', 422, details={
            'limit': 'normalized_field_bytes', 'field': path,
            'max_bytes': MAX_NORMALIZED_FIELD_BYTES})


def check_normalized_field(path: str, value: Any) -> int:
    size = normalized_utf8_bytes(value)
    _check_normalized_field_bytes(path, size)
    return size


def _accumulate_list_row(path: str, size: int, count: int, row: dict) -> int:
    # Brackets plus canonical rows and commas equal the final list's JSON size.
    size += normalized_utf8_bytes(row) + (1 if count else 0)
    _check_normalized_field_bytes(path, size)
    return size


class NormalizedResultBudget:
    """Account for the exact canonical result size as top-level fields arrive."""

    def __init__(self) -> None:
        self._size = 2  # Empty JSON object braces.
        self._count = 0

    def add(self, name: str, value: Any) -> None:
        value_size = check_normalized_field(name, value)
        entry_size = normalized_utf8_bytes(name) + 1 + value_size + (1 if self._count else 0)
        if self._size + entry_size > MAX_NORMALIZED_RESULT_BYTES:
            raise DomainError('collection_limit', 422, details={
                'limit': 'normalized_result_bytes', 'field': name,
                'max_bytes': MAX_NORMALIZED_RESULT_BYTES})
        self._size += entry_size
        self._count += 1


def validate_normalized_result(fields: dict) -> None:
    budget = NormalizedResultBudget()
    for name, value in fields.items():
        budget.add(name, value)


def normalize_text(value: str, normal: Normalization) -> str:
    if normal.trim:
        value = value.strip()
    if normal.collapse_whitespace:
        value = ' '.join(value.split())
    return value


def _decimal(value: str, field: FieldSpec, path: str) -> str:
    normal = field.normalize
    decimal = re.escape(normal.decimal_separator)
    thousands = normal.thousands_separator
    integer = r'[0-9]+'
    if thousands is not None:
        separator = re.escape(thousands)
        integer = rf'(?:[0-9]+|[0-9]{{1,3}}(?:{separator}[0-9]{{3}})+)'
    # No exponent, guessing, NaN, trailing junk, or malformed grouping.
    if not re.fullmatch(rf'[+-]?{integer}(?:{decimal}[0-9]+)?', value):
        invalid(path, 'invalid_number')
    if thousands is not None:
        value = value.replace(thousands, '')
    value = value.replace(normal.decimal_separator, '.')
    try:
        number = Decimal(value)
    except InvalidOperation:
        invalid(path, 'invalid_number')
    if not number.is_finite():
        invalid(path, 'invalid_number')
    return format(number, 'f')


def _money(value: str, field: FieldSpec, path: str) -> dict:
    currency = field.normalize.currency
    # A currency marker is optional for numeric attributes; if visible it must
    # agree, not be discarded as generic nonnumeric decoration.
    marker = re.match(r'^([A-Za-z]{1,3}\$|[A-Za-z]{3}|[^\d+\-.,\s])\s*', value)
    suffix = re.search(r'\s*([A-Za-z]{3}|[^0-9.,\s])$', value)
    if marker:
        token = marker.group(1)
        value = value[marker.end():]
    elif suffix:
        token = suffix.group(1)
        value = value[:suffix.start()]
    else:
        token = None
    if token is not None and token != currency and currency not in _CURRENCY_SYMBOLS.get(token, ()):
        invalid(path, 'currency_mismatch')
    return {'amount': _decimal(value, field, path), 'currency': currency}


def _date(value: str, field: FieldSpec, path: str) -> str:
    normal = field.normalize
    try:
        parsed = datetime.strptime(value, normal.date_format)
        if parsed.tzinfo is None:
            zone = ZoneInfo(normal.timezone)
            # Do not guess at nonexistent or repeated local times around DST.
            candidates = set()
            for fold in (0, 1):
                local = parsed.replace(tzinfo=zone, fold=fold)
                utc = local.astimezone(UTC)
                if utc.astimezone(zone).replace(tzinfo=None) == parsed:
                    candidates.add(utc)
            if len(candidates) != 1:
                invalid(path, 'ambiguous_or_nonexistent_date')
            parsed = candidates.pop()
        return parsed.astimezone(UTC).isoformat().replace('+00:00', 'Z')
    except (ValueError, OverflowError):
        invalid(path, 'invalid_date')


def _scalar(value: str, field: FieldSpec, final_url: str, path: str):
    value = normalize_text(value, field.normalize)
    if value == '' and field.required and not field.allow_empty:
        invalid(path, 'required_empty')
    if field.type == 'text':
        return value
    if field.type == 'number':
        return _decimal(value, field, path)
    if field.type == 'money':
        return _money(value, field, path)
    if field.type == 'date':
        return _date(value, field, path)
    if field.type == 'boolean':
        if value in field.normalize.true_values:
            return True
        if value in field.normalize.false_values:
            return False
        invalid(path, 'invalid_boolean')
    if field.type == 'url':
        if not value:
            invalid(path, 'invalid_url')
        return validate_url(urljoin(final_url, value))
    invalid(path, 'unsupported_type')


def _text_of(value: Any, path: str, reason: str) -> str:
    """String form of a JSON scalar; objects and arrays have no textual form."""
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return format(Decimal(str(value)), 'f')
    if isinstance(value, str):
        return value
    invalid(path, reason)


def normalize_json_scalar(value: Any, field: FieldSpec, final_url: str, path: str):
    """Apply one normalization contract to HTML text and to native JSON values."""
    if value is None:
        if field.allow_empty and field.type == 'list':
            return []
        if field.allow_empty and field.type == 'text':
            return ''
        if field.required:
            invalid(path, 'required_missing')
        return MISSING
    if field.type == 'boolean' and isinstance(value, bool):
        return value
    if field.type == 'text':
        text = normalize_text(_text_of(value, path, 'invalid_text'), field.normalize)
        if text == '' and field.required and not field.allow_empty:
            invalid(path, 'required_empty')
        return text
    if field.type == 'number':
        return _decimal(normalize_text(_text_of(value, path, 'invalid_number'),
                                       field.normalize), field, path)
    if field.type == 'money':
        return _money(normalize_text(_text_of(value, path, 'invalid_money'),
                                     field.normalize), field, path)
    if field.type == 'date':
        return _date(normalize_text(_text_of(value, path, 'invalid_date'),
                                    field.normalize), field, path)
    if field.type == 'boolean':
        text = normalize_text(_text_of(value, path, 'invalid_boolean'), field.normalize)
        if text in field.normalize.true_values:
            return True
        if text in field.normalize.false_values:
            return False
        invalid(path, 'invalid_boolean')
    if field.type == 'url':
        text = normalize_text(_text_of(value, path, 'invalid_url'), field.normalize)
        if not text:
            invalid(path, 'invalid_url')
        return validate_url(urljoin(final_url, text))
    invalid(path, 'unsupported_type')


def _extract(root: BeautifulSoup | Tag, field: FieldSpec, final_url: str, path: str):
    # A row's own attributes/text are selectable without escaping its scope.
    matches = [root] if field.selector == ':scope' and isinstance(root, Tag) and not isinstance(root, BeautifulSoup) else root.select(field.selector)
    if field.type == 'list':
        check_raw_list_size(field, path, len(matches))
        rows = []
        normalized_size = 2
        for index, row in enumerate(matches):
            values = {}
            for item in field.item_fields:
                value = _extract(row, item, final_url, f'{path}[{index}].{item.name}')
                if value is not MISSING:
                    values[item.name] = value
            normalized_size = _accumulate_list_row(path, normalized_size, index, values)
            rows.append(values)
        return rows
    if len(matches) > 1:
        invalid(path, 'multiple_matches')
    if not matches:
        if field.required:
            invalid(path, 'required_missing')
        if field.allow_empty and field.type == 'text':
            return ''
        return MISSING
    element = matches[0]
    if field.attribute is None:
        value = element.get_text(separator='')
    else:
        value = element.get(field.attribute, MISSING)
        if value is MISSING:
            if field.required:
                invalid(path, 'required_missing')
            return MISSING
        if isinstance(value, list):
            value = ' '.join(value)
    normalized = _scalar(value, field, final_url, path)
    check_normalized_field(path, normalized)
    return normalized


def extract_fields(html: str, spec: MonitorSpec, final_url: str) -> dict:
    """Extract JSON-safe values; validate merged rows separately before commit."""

    root = BeautifulSoup(html, 'lxml')
    fields = {}
    budget = NormalizedResultBudget()
    for field in spec.fields:
        value = _extract(root, field, final_url, field.name)
        if value is not MISSING:
            budget.add(field.name, value)
            fields[field.name] = value
    return fields
