"""Deterministic extraction from parsed JSON, plus a bounded structural summary.

Paths are normalized at spec validation (`FieldSpec.path`), so nothing here
cleans them again. Only dot keys and numeric indices are addressable.
"""
import re
from typing import Any

from webmonitor.collection.extraction import MISSING, invalid, normalize_json_scalar
from webmonitor.schemas.monitors import FieldSpec, MonitorSpec

_SEGMENT = re.compile(r'[A-Za-z0-9_$-]+|\[(\d+)\]')
MAX_KEYS = 20
MAX_ENTRIES = 50
MAX_DEPTH = 3
MAX_LISTS = 8
MAX_HINTS = 12
PAGINATION_KEYS = frozenset({
    'count', 'total', 'pages', 'next', 'prev', 'no_more', 'has_more', 'page', 'limit',
    'pagesize', 'totalpages', 'current',
})


def resolve_path(value: Any, path: str) -> Any:
    """Walk dict keys and list indices; missing structure raises naturally."""
    for segment in _SEGMENT.finditer(path):
        index = segment.group(1)
        value = value[int(index)] if index is not None else value[segment.group(0)]
    return value


def _row(row: dict, field: FieldSpec, final_url: str, path: str) -> dict:
    values = {}
    for item in field.item_fields or []:
        item_path = f'{path}.{item.name}'
        try:
            raw = resolve_path(row, item.path)
        except (KeyError, IndexError, TypeError):
            if item.required:
                invalid(item_path, 'required_missing')
            continue
        value = normalize_json_scalar(raw, item, final_url, item_path)
        if value is not MISSING:
            values[item.name] = value
    return values


def extract_json_field(body: Any, field: FieldSpec, final_url: str, path: str):
    try:
        value = resolve_path(body, field.path)
    except (KeyError, IndexError, TypeError):
        if field.required:
            invalid(path, 'required_missing')
        return MISSING
    if field.type != 'list':
        return normalize_json_scalar(value, field, final_url, path)
    if not isinstance(value, list):
        invalid(path, 'invalid_list')
    rows = []
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            invalid(path, 'invalid_row')
        rows.append(_row(row, field, final_url, f'{path}[{index}]'))
    return rows


def extract_json_fields(body: Any, spec: MonitorSpec, final_url: str | None = None) -> dict:
    base = final_url or spec.url
    fields = {}
    for field in spec.fields:
        value = extract_json_field(body, field, base, field.name)
        if value is not MISSING:
            fields[field.name] = value
    return fields


def _hint_key(key: str) -> bool:
    return key.lower() in PAGINATION_KEYS


def json_summary(body: Any) -> dict:
    """Describe shape, candidate lists and pagination hints; never raise."""
    root = 'object' if isinstance(body, dict) else 'array' if isinstance(body, list) else 'scalar'
    summary = {
        'root': root,
        'keys': list(body)[:MAX_KEYS] if isinstance(body, dict) else [],
        'lists': [],
        'pagination': [],
    }
    lists, hints = summary['lists'], summary['pagination']

    def walk(value: Any, path: str, depth: int) -> None:
        if not isinstance(value, (dict, list)):
            return
        if len(lists) >= MAX_LISTS and len(hints) >= MAX_HINTS:
            return
        if isinstance(value, list):
            if value and all(isinstance(item, dict) for item in value):
                if len(lists) < MAX_LISTS:
                    lists.append({'path': path, 'count': len(value),
                                  'item_keys': list(value[0])[:MAX_KEYS]})
            if value and depth < MAX_DEPTH:
                walk(value[0], f'{path}[0]', depth + 1)
            return
        for key, item in list(value.items())[:MAX_ENTRIES]:
            child = f'{path}.{key}' if path else str(key)
            if len(hints) < MAX_HINTS and _hint_key(str(key)) and child.count('.') <= 1:
                if item is None or isinstance(item, (str, int, float, bool)):
                    hints.append({'path': child, 'value': item})
            if depth < MAX_DEPTH:
                walk(item, child, depth + 1)

    try:
        walk(body, '', 0)
    except Exception:
        # A summary is advisory; odd payloads must never fail a probe or replay.
        pass
    return summary
