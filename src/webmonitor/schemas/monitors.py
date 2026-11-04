"""Validated monitor configuration shared by HTTP, Agent and workers."""
import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, StrictBool, field_validator, model_validator

from webmonitor.schemas.notifications import Contract

# ISO 4217 monetary codes, including fund/metal units and no-currency XXX.
ISO_CURRENCIES = frozenset(['AED', 'AFN', 'ALL', 'AMD', 'ANG', 'AOA', 'ARS', 'AUD', 'AWG', 'AZN', 'BAM', 'BBD', 'BDT', 'BGN', 'BHD', 'BIF', 'BMD', 'BND', 'BOB', 'BOV', 'BRL', 'BSD', 'BTN', 'BWP', 'BYN', 'BZD', 'CAD', 'CDF', 'CHE', 'CHF', 'CHW', 'CLF', 'CLP', 'CNY', 'COP', 'COU', 'CRC', 'CUP', 'CVE', 'CZK', 'DJF', 'DKK', 'DOP', 'DZD', 'EGP', 'ERN', 'ETB', 'EUR', 'FJD', 'FKP', 'GBP', 'GEL', 'GHS', 'GIP', 'GMD', 'GNF', 'GTQ', 'GYD', 'HKD', 'HNL', 'HTG', 'HUF', 'IDR', 'ILS', 'INR', 'IQD', 'IRR', 'ISK', 'JMD', 'JOD', 'JPY', 'KES', 'KGS', 'KHR', 'KMF', 'KPW', 'KRW', 'KWD', 'KYD', 'KZT', 'LAK', 'LBP', 'LKR', 'LRD', 'LSL', 'LYD', 'MAD', 'MDL', 'MGA', 'MKD', 'MMK', 'MNT', 'MOP', 'MRU', 'MUR', 'MVR', 'MWK', 'MXN', 'MXV', 'MYR', 'MZN', 'NAD', 'NGN', 'NIO', 'NOK', 'NPR', 'NZD', 'OMR', 'PAB', 'PEN', 'PGK', 'PHP', 'PKR', 'PLN', 'PYG', 'QAR', 'RON', 'RSD', 'RUB', 'RWF', 'SAR', 'SBD', 'SCR', 'SDG', 'SEK', 'SGD', 'SHP', 'SLE', 'SOS', 'SRD', 'SSP', 'STN', 'SVC', 'SYP', 'SZL', 'THB', 'TJS', 'TMT', 'TND', 'TOP', 'TRY', 'TTD', 'TWD', 'TZS', 'UAH', 'UGX', 'USD', 'USN', 'UYI', 'UYU', 'UYW', 'UZS', 'VED', 'VES', 'VND', 'VUV', 'WST', 'XAF', 'XAG', 'XAU', 'XBA', 'XBB', 'XBC', 'XBD', 'XCD', 'XCG', 'XDR', 'XOF', 'XPD', 'XPF', 'XPT', 'XSU', 'XTS', 'XUA', 'XXX', 'YER', 'ZAR', 'ZMW', 'ZWG'])


def _canonical(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonical(value.model_dump(mode='python'))
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError('non-finite decimal')
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError('datetime must have a timezone')
        return value.astimezone(UTC).isoformat().replace('+00:00', 'Z')
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError('JSON object keys must be strings')
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_canonical(value), ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def _timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError('timezone must be an IANA identifier') from exc
    return value


# Request headers are replayed only from this fixed set; credentials never travel.
REQUEST_HEADER_ALLOWLIST = frozenset({
    'accept', 'accept-language', 'content-type', 'user-agent',
    'referer', 'origin', 'x-requested-with',
})
# A step may substitute a scalar from an earlier response into a later URL.
REQUEST_TEMPLATE = re.compile(
    r'\{\{steps\.(?P<step>[a-z][a-z0-9_]{0,31})\.'
    r'(?P<path>[A-Za-z0-9_$-]+(?:\.[A-Za-z0-9_$-]+|\[\d+\])*)\}\}')
JSON_PATH = re.compile(r'^[A-Za-z0-9_$-]+(?:\.[A-Za-z0-9_$-]+|\[\d+\])*$')
# soupsieve implements jQuery-style pseudos that Chromium does not.
SOUPSIEVE_ONLY = re.compile(r":(-soup|contains|nth-last-column|matches)\b", re.IGNORECASE)


def clean_json_path(value: str) -> str:
    """Normalize `$.data.list` and reject expressions, wildcards and empty paths."""
    value = value[2:] if value.startswith('$.') else value
    if not JSON_PATH.fullmatch(value):
        raise ValueError('JSON paths use keys and numeric indices only')
    return value


def validate_http_url(value: str) -> str:
    from urllib.parse import urlsplit
    try:
        parsed = urlsplit(value)
        _ = parsed.port  # Force malformed port validation; egress owns port policy.
    except ValueError as exc:
        raise ValueError('invalid HTTP(S) URL') from exc
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError('HTTP(S) URL without user information required')
    return value


def _static_authority(value: str) -> None:
    """Templates belong in the path or query; the host must be a literal."""
    start = value.find('://')
    if start < 0:
        return
    tail = value[start + 3:]
    end = len(tail)
    for stop in '/?#':
        index = tail.find(stop)
        if index >= 0:
            end = min(end, index)
    if '{{' in tail[:end]:
        raise ValueError('request URL templates must stay in the path or query')


class Normalization(Contract):
    trim: StrictBool = True
    collapse_whitespace: StrictBool = False
    decimal_separator: Literal['.', ','] | None = None
    thousands_separator: Literal['.', ',', ' ', "'"] | None = None
    currency: str | None = Field(default=None, pattern=r'^[A-Z]{3}$')
    date_format: str | None = Field(default=None, min_length=1, max_length=100)
    timezone: str | None = None
    true_values: list[str] = Field(default_factory=list)
    false_values: list[str] = Field(default_factory=list)

    @field_validator('currency')
    @classmethod
    def valid_currency(cls, value: str | None) -> str | None:
        if value is not None and value not in ISO_CURRENCIES:
            raise ValueError('currency must be an ISO 4217 code')
        return value

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        return _timezone(value) if value is not None else None

    @model_validator(mode='after')
    def unambiguous(self) -> 'Normalization':
        if self.thousands_separator is not None and self.thousands_separator == self.decimal_separator:
            raise ValueError('decimal and thousands separators must differ')
        values = self.true_values + self.false_values
        if self.trim:
            values = [value.strip() for value in values]
        if self.collapse_whitespace:
            values = [' '.join(value.split()) for value in values]
        if len(set(values)) != len(values):
            raise ValueError('boolean values must be distinct and disjoint')
        split = len(self.true_values)
        self.true_values = values[:split]
        self.false_values = values[split:]
        return self


class FieldSpec(Contract):
    name: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_]{0,63}$')
    type: Literal['text', 'number', 'money', 'date', 'boolean', 'url', 'list']
    semantic: str = Field(min_length=1, max_length=500)
    selector: str | None = Field(default=None, min_length=1, max_length=1000)
    path: str | None = Field(default=None, min_length=1, max_length=500)
    attribute: str | None = Field(default=None, pattern=r'^[A-Za-z_][A-Za-z0-9_:-]*$')
    required: StrictBool = True
    allow_empty: StrictBool = False
    normalize: Normalization = Field(default_factory=Normalization)
    item_fields: list['FieldSpec'] | None = None
    min_items: int | None = Field(default=None, ge=0, strict=True)
    max_items: int | None = Field(default=None, ge=0, strict=True)

    @field_validator('attribute', mode='before')
    @classmethod
    def empty_attribute(cls, value: Any) -> Any:
        return None if value == '' else value

    @field_validator('selector')
    @classmethod
    def css_only(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value or value.startswith(('/', 'xpath=', 'javascript:', 'js=')) or '::' in value:
            raise ValueError('only CSS element selectors are supported')
        # Parse CSS without allowing XPath, script or expressions.
        import soupsieve
        try:
            soupsieve.compile(value)
        except soupsieve.SelectorSyntaxError as exc:
            raise ValueError('invalid CSS selector') from exc
        # The browser executes the same string, so selectors only soupsieve
        # understands would silently select nothing in Chromium.
        if SOUPSIEVE_ONLY.search(value):
            raise ValueError('only selectors supported by browsers are allowed')
        return value

    @field_validator('path')
    @classmethod
    def path_only(cls, value: str | None) -> str | None:
        return None if value is None else clean_json_path(value.strip())

    @model_validator(mode='after')
    def type_contract(self) -> 'FieldSpec':
        if (self.selector is None) == (self.path is None):
            raise ValueError('field requires exactly one of selector or path')
        if self.path is not None and self.attribute is not None:
            raise ValueError('attribute applies only to selector fields')
        if self.allow_empty and self.type not in ('text', 'list'):
            raise ValueError('allow_empty applies only to text and list fields')
        normal = self.normalize
        if self.type == 'list':
            if not self.item_fields or self.attribute is not None:
                raise ValueError('list requires item_fields and cannot use an attribute')
            if any(item.type == 'list' for item in self.item_fields):
                raise ValueError('nested lists are not supported')
            if len({item.name for item in self.item_fields}) != len(self.item_fields):
                raise ValueError('duplicate item field name')
            if self.min_items is not None and self.max_items is not None and self.min_items > self.max_items:
                raise ValueError('min_items exceeds max_items')
            if self.allow_empty and self.min_items:
                raise ValueError('allow_empty requires min_items 0 or unset')
        elif self.item_fields is not None or self.min_items is not None or self.max_items is not None:
            raise ValueError('item_fields and item limits apply only to lists')
        if self.type in ('number', 'money'):
            if normal.decimal_separator is None:
                raise ValueError('numeric fields require an explicit decimal_separator')
        elif normal.decimal_separator is not None or normal.thousands_separator is not None:
            raise ValueError('numeric separators apply only to number/money')
        if self.type == 'money':
            if normal.currency is None:
                raise ValueError('money requires an explicit ISO currency')
        elif normal.currency is not None:
            raise ValueError('currency applies only to money')
        if self.type == 'date':
            if normal.date_format is None or normal.timezone is None:
                raise ValueError('date requires an explicit date_format and timezone')
        elif normal.date_format is not None or normal.timezone is not None:
            raise ValueError('date configuration applies only to dates')
        if self.type == 'boolean':
            if not normal.true_values or not normal.false_values:
                raise ValueError('boolean requires true_values and false_values')
        elif normal.true_values or normal.false_values:
            raise ValueError('boolean values apply only to boolean fields')
        return self


class BusinessKey(Contract):
    field: str
    item_fields: list[str] = Field(min_length=1)

    @field_validator('item_fields')
    @classmethod
    def unique_fields(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError('duplicate business key field')
        return value


class Coverage(Contract):
    scope: Literal['full', 'bounded']
    description: str = Field(min_length=1, max_length=2000)


class RuleBase(Contract):
    field: str


class TextChanged(RuleBase):
    type: Literal['text_changed']


class KeywordPresent(RuleBase):
    type: Literal['keyword_present']
    keyword: str = Field(min_length=1)


class KeywordAbsent(RuleBase):
    type: Literal['keyword_absent']
    keyword: str = Field(min_length=1)


class NumericChange(RuleBase):
    operator: Literal['increase_gte', 'decrease_gte', 'change_gte']
    value: Decimal = Field(gt=0, allow_inf_nan=False)


class NumberAbsoluteChange(NumericChange):
    type: Literal['number_absolute_change']


class NumberPercentChange(NumericChange):
    type: Literal['number_percent_change']


class Threshold(RuleBase):
    type: Literal['threshold']
    operator: Literal['gt', 'gte', 'lt', 'lte', 'eq']
    value: Decimal = Field(allow_inf_nan=False)


class ListAdded(RuleBase):
    type: Literal['list_added']


class ListRemoved(RuleBase):
    type: Literal['list_removed']


class ListUpdated(RuleBase):
    type: Literal['list_updated']
    watch_fields: list[str] = Field(min_length=1)

    @field_validator('watch_fields')
    @classmethod
    def unique_fields(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError('duplicate watch field')
        return value


ChangeRule = Annotated[TextChanged | KeywordPresent | KeywordAbsent | NumberAbsoluteChange | NumberPercentChange | Threshold | ListAdded | ListRemoved | ListUpdated, Field(discriminator='type')]


class ChangeRules(Contract):
    mode: Literal['all', 'any']
    rules: list[ChangeRule] = Field(min_length=1)


class Schedule(Contract):
    interval_seconds: int = Field(ge=60, le=86400, strict=True)
    timezone: str

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        return _timezone(value)


class WaitForSelector(Contract):
    type: Literal['wait_for_selector']
    selector: str
    timeout_ms: int = Field(default=10000, gt=0, le=10000, strict=True)

    @field_validator('selector')
    @classmethod
    def valid_selector(cls, value: str) -> str:
        return FieldSpec.css_only(value)


class Scroll(Contract):
    type: Literal['scroll']
    max_steps: int = Field(ge=1, le=5, strict=True)


class ClickNext(Contract):
    type: Literal['click_next']
    selector: str
    max_pages: int = Field(ge=1, le=3, strict=True)

    @field_validator('selector')
    @classmethod
    def valid_selector(cls, value: str) -> str:
        return FieldSpec.css_only(value)


BrowserStep = Annotated[WaitForSelector | Scroll | ClickNext, Field(discriminator='type')]


class ApiRequest(Contract):
    method: Literal['GET', 'POST'] = 'GET'
    url: str = Field(min_length=1, max_length=4096)
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any | None = None

    @field_validator('url')
    @classmethod
    def request_url(cls, value: str) -> str:
        value = validate_http_url(value)
        _static_authority(value)
        return value

    @field_validator('headers')
    @classmethod
    def request_headers(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 10:
            raise ValueError('at most 10 request headers are supported')
        folded: dict[str, str] = {}
        for name, item in value.items():
            key = name.strip().casefold()
            if key not in REQUEST_HEADER_ALLOWLIST:
                raise ValueError(f'{name} is not a supported request header')
            if key in folded:
                raise ValueError('duplicate request header')
            if not isinstance(item, str) or not 1 <= len(item) <= 1000 or '\r' in item or '\n' in item:
                raise ValueError('invalid request header value')
            if '{{' in item:
                raise ValueError('templates are supported in request URLs only')
            folded[key] = item
        return folded

    @model_validator(mode='after')
    def body_contract(self) -> 'ApiRequest':
        content_type = self.headers.get('content-type')
        if content_type is not None and content_type.split(';', 1)[0].strip().lower() != 'application/json':
            raise ValueError('request bodies must be application/json')
        if self.method == 'GET':
            if self.body is not None:
                raise ValueError('GET requests cannot carry a body')
            return self
        if self.body is not None:
            if not isinstance(self.body, (dict, list)):
                raise ValueError('request bodies must be a JSON object or array')
            encoded = canonical_json(self.body)
            if len(encoded.encode('utf-8')) > 16384:
                raise ValueError('request body exceeds 16384 bytes')
            if '{{' in encoded:
                raise ValueError('templates are supported in request URLs only')
        return self


class SourceStep(Contract):
    id: str = Field(pattern=r'^[a-z][a-z0-9_]{0,31}$')
    request: ApiRequest


class JsonEqualsAssertion(Contract):
    type: Literal['json_equals']
    path: str = Field(min_length=1, max_length=500)
    equals: str | int | float | bool | None

    @field_validator('path')
    @classmethod
    def valid_path(cls, value: str) -> str:
        return clean_json_path(value.strip())


class JsonPresentAssertion(Contract):
    type: Literal['json_present']
    path: str = Field(min_length=1, max_length=500)

    @field_validator('path')
    @classmethod
    def valid_path(cls, value: str) -> str:
        return clean_json_path(value.strip())


Assertion = Annotated[JsonEqualsAssertion | JsonPresentAssertion, Field(discriminator='type')]


class PagePagination(Contract):
    kind: Literal['page'] = 'page'
    page_param: str = Field(default='page', pattern=r'^[A-Za-z][A-Za-z0-9_]{0,31}$')
    start_page: int = Field(default=1, ge=1, le=10000, strict=True)
    size_param: str | None = Field(default=None, pattern=r'^[A-Za-z][A-Za-z0-9_]{0,31}$')
    size: int | None = Field(default=None, ge=1, le=1000, strict=True)
    total_path: str | None = Field(default=None, min_length=1, max_length=500)
    stop: Literal['empty', 'total_reached'] = 'empty'
    max_pages: int = Field(default=3, ge=1, le=5, strict=True)
    max_items: int = Field(default=500, ge=1, le=2000, strict=True)

    @field_validator('total_path')
    @classmethod
    def valid_total_path(cls, value: str | None) -> str | None:
        return None if value is None else clean_json_path(value.strip())


class ApiSource(Contract):
    kind: Literal['json'] = 'json'
    steps: list[SourceStep] = Field(min_length=1, max_length=3)
    assertions: list[Assertion] = Field(default_factory=list, max_length=8)
    pagination: PagePagination | None = None

    @model_validator(mode='after')
    def ordered_steps(self) -> 'ApiSource':
        declared: set[str] = set()
        for step in self.steps:
            if step.id in declared:
                raise ValueError('duplicate step id')
            referenced = {match.group('step') for match in REQUEST_TEMPLATE.finditer(step.request.url)}
            if not referenced <= declared:
                raise ValueError('templates may reference an earlier step only')
            declared.add(step.id)
        return self


class MonitorSpec(Contract):
    """The collection contract only; recipients, cadence and mail are user settings."""

    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=4096)
    collection_mode: Literal['http', 'browser']
    fields: list[FieldSpec] = Field(min_length=1)
    business_key: BusinessKey | None = None
    change_rules: ChangeRules
    coverage: Coverage
    browser_steps: list[BrowserStep] = Field(default_factory=list)
    source: ApiSource | None = None

    @field_validator('url')
    @classmethod
    def http_url(cls, value: str) -> str:
        return validate_http_url(value)

    @model_validator(mode='after')
    def references(self) -> 'MonitorSpec':
        fields = {field.name: field for field in self.fields}
        if len(fields) != len(self.fields):
            raise ValueError('duplicate field name')
        if self.collection_mode == 'http' and self.browser_steps:
            raise ValueError('browser_steps require browser collection mode')
        self._channel_fields()
        if any(field.type == 'list' for field in self.fields) and self.business_key is None:
            raise ValueError('list fields require a designated business_key')
        if self.business_key:
            target = fields.get(self.business_key.field)
            if target is None or target.type != 'list':
                raise ValueError('business_key must reference a list field')
            items = {item.name: item for item in target.item_fields or []}
            for key in self.business_key.item_fields:
                if key not in items or not items[key].required:
                    raise ValueError('business key fields must exist and be required')
        for rule in self.change_rules.rules:
            target = fields.get(rule.field)
            if target is None:
                raise ValueError('rule references missing field')
            if rule.type in ('text_changed', 'keyword_present', 'keyword_absent') and target.type != 'text':
                raise ValueError('text rules require a text field')
            if rule.type in ('number_absolute_change', 'number_percent_change', 'threshold') and target.type not in ('number', 'money'):
                raise ValueError('numeric rules require number/money field')
            if rule.type.startswith('list_'):
                if target.type != 'list' or self.business_key is None or self.business_key.field != rule.field:
                    raise ValueError('list rules require the designated business_key list')
                if rule.type == 'list_removed' and not target.allow_empty:
                    raise ValueError('list deletion requires allow_empty on the list field')
                if isinstance(rule, ListUpdated):
                    item_names = {item.name for item in target.item_fields or []}
                    if not set(rule.watch_fields) <= item_names or set(rule.watch_fields) & set(self.business_key.item_fields):
                        raise ValueError('watch_fields must be existing non-business-key fields')
        return self

    def _channel_fields(self) -> None:
        """One channel per spec: HTML selectors or JSON paths, never both."""
        if self.source is not None:
            if self.collection_mode != 'http' or self.browser_steps:
                raise ValueError('source requires http mode without browser steps')
            for field in self.fields:
                if field.path is None or field.selector is not None:
                    raise ValueError('json sources require path fields')
                if any(item.path is None or item.selector is not None
                       for item in field.item_fields or []):
                    raise ValueError('json sources require path fields')
            pagination = self.source.pagination
            if pagination is not None:
                if sum(field.type == 'list' for field in self.fields) != 1:
                    raise ValueError('page pagination requires one list field')
                if pagination.stop == 'total_reached' and pagination.total_path is None:
                    raise ValueError('total_reached requires total_path')
                if (pagination.size_param is None) != (pagination.size is None):
                    raise ValueError('size_param and size must be set together')
            return
        for field in self.fields:
            if field.selector is None or field.path is not None:
                raise ValueError('html sources require selector fields')
            if any(item.selector is None or item.path is not None
                   for item in field.item_fields or []):
                raise ValueError('html sources require selector fields')

