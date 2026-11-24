"""Consumer-visible baseline and event transition boundaries."""

import json

import pytest
from pydantic import ValidationError

from webmonitor.collection.diff import evaluate_rules
from webmonitor.schemas.monitors import MonitorSpec


def make_spec(fields, rules, *, business_key=None, mode='any', consecutive_hits=1):
    return MonitorSpec.model_validate({
        'name': 'Regression monitor', 'url': 'https://example.com/product',
        'collection_mode': 'http', 'fields': fields, 'business_key': business_key,
        'change_rules': {'mode': mode, 'rules': rules, 'consecutive_hits': consecutive_hits},
        'coverage': {'scope': 'full', 'description': 'Complete product list'},
    })


def number_spec(rule):
    return make_spec([{'name': 'price', 'type': 'number', 'semantic': 'Current price',
                       'selector': '.price', 'normalize': {'decimal_separator': '.'}}], [rule])


def scalar_spec(kind, rule, *, consecutive_hits=1):
    normalize = {}
    if kind == 'date':
        normalize = {'date_format': '%Y-%m-%d', 'timezone': 'UTC'}
    elif kind == 'boolean':
        normalize = {'true_values': ['yes'], 'false_values': ['no']}
    elif kind == 'number':
        normalize = {'decimal_separator': '.'}
    return make_spec([{'name': 'value', 'type': kind, 'semantic': 'Current value',
                       'selector': '.value', 'normalize': normalize}],
                     [{**rule, 'field': 'value'}], consecutive_hits=consecutive_hits)


def test_percent_zero_is_undefined_then_uses_latest_success():
    spec = number_spec({'type': 'number_percent_change', 'field': 'price',
                        'operator': 'decrease_gte', 'value': '10'})
    initialized = evaluate_rules(spec, None, {'price': '0'}, {})
    assert initialized['triggered'] is False
    undefined = evaluate_rules(spec, {'price': '0'}, {'price': '100'}, initialized['rule_state'])
    assert undefined['triggered'] is False
    assert undefined['warnings'] == [{'code': 'rule_undefined', 'rule_index': 0,
                                      'field': 'price', 'reason': 'previous_zero'}]
    dropped = evaluate_rules(spec, {'price': '100'}, {'price': '80'}, undefined['rule_state'])
    assert dropped['triggered'] is True
    assert dropped['differences'][0]['before'] == '100'
    unchanged = evaluate_rules(spec, {'price': '80'}, {'price': '80'}, dropped['rule_state'])
    assert unchanged['triggered'] is False


def test_negative_previous_percent_uses_absolute_denominator():
    spec = number_spec({'type': 'number_percent_change', 'field': 'price',
                        'operator': 'increase_gte', 'value': '10'})
    result = evaluate_rules(spec, {'price': '-100'}, {'price': '-80'}, {})
    assert result['triggered'] is True


def test_successive_list_additions_each_emit_only_new_rows():
    spec = make_spec([
        {'name': 'products', 'type': 'list', 'semantic': 'Products', 'selector': '.product',
         'item_fields': [{'name': 'id', 'type': 'text', 'semantic': 'Stable ID', 'selector': '.id'},
                         {'name': 'title', 'type': 'text', 'semantic': 'Title', 'selector': '.title'}]}
    ], [{'type': 'list_added', 'field': 'products'}],
       business_key={'field': 'products', 'item_fields': ['id']})
    a = {'id': 'A', 'title': 'Alpha'}
    b = {'id': 'B', 'title': 'Beta'}
    c = {'id': 'C', 'title': 'Gamma'}
    state = evaluate_rules(spec, None, {'products': [a]}, {})
    assert state['triggered'] is False
    added_b = evaluate_rules(spec, {'products': [a]}, {'products': [a, b]}, state['rule_state'])
    assert added_b['event_type'] == 'list_changed'
    assert added_b['differences'][0]['items'] == [b]
    added_c = evaluate_rules(spec, {'products': [a, b]}, {'products': [a, b, c]}, added_b['rule_state'])
    assert added_c['triggered'] is True
    assert added_c['differences'][0]['items'] == [c]
    unchanged = evaluate_rules(spec, {'products': [a, b, c]}, {'products': [a, b, c]}, added_c['rule_state'])
    assert unchanged['triggered'] is False


def test_threshold_initial_true_and_continuous_true_do_not_notify():
    spec = number_spec({'type': 'threshold', 'field': 'price', 'operator': 'gte', 'value': '100'})
    initial = evaluate_rules(spec, None, {'price': '110'}, {})
    assert initial['triggered'] is False
    sustained = evaluate_rules(spec, {'price': '110'}, {'price': '120'}, initial['rule_state'])
    assert sustained['triggered'] is False
    off = evaluate_rules(spec, {'price': '120'}, {'price': '90'}, sustained['rule_state'])
    assert off['triggered'] is False
    on = evaluate_rules(spec, {'price': '90'}, {'price': '100'}, off['rule_state'])
    assert on['triggered'] is True
    assert on['event_type'] == 'content_changed'


def test_persistent_predicate_does_not_swallow_new_change_in_mixed_any_rules():
    spec = make_spec([
        {'name': 'price', 'type': 'number', 'semantic': 'Current price', 'selector': '.price',
         'normalize': {'decimal_separator': '.'}},
        {'name': 'title', 'type': 'text', 'semantic': 'Title', 'selector': '.title'},
    ], [
        {'type': 'threshold', 'field': 'price', 'operator': 'gte', 'value': '100'},
        {'type': 'text_changed', 'field': 'title'},
    ])
    initial = evaluate_rules(spec, None, {'price': '100', 'title': 'A'}, {})
    unchanged = evaluate_rules(spec, {'price': '100', 'title': 'A'},
                               {'price': '100', 'title': 'A'}, initial['rule_state'])
    assert unchanged['triggered'] is False
    first = evaluate_rules(spec, {'price': '100', 'title': 'A'},
                           {'price': '100', 'title': 'B'}, unchanged['rule_state'])
    second = evaluate_rules(spec, {'price': '100', 'title': 'B'},
                            {'price': '100', 'title': 'C'}, first['rule_state'])
    assert first['triggered'] is True
    assert second['triggered'] is True
    assert [item['type'] for item in second['differences']] == ['threshold', 'text_changed']
    assert second['differences'][1]['before'] == 'B'


def test_list_deletion_requires_allow_empty_and_the_designated_list():
    import pytest
    from pydantic import ValidationError

    row = [{'name': 'id', 'type': 'text', 'semantic': 'ID', 'selector': '.id'}]
    spec = make_spec([
        {'name': 'products', 'type': 'list', 'semantic': 'Products', 'selector': '.product',
         'item_fields': row, 'allow_empty': True},
        {'name': 'related', 'type': 'list', 'semantic': 'Related', 'selector': '.related', 'item_fields': row},
    ], [{'type': 'list_removed', 'field': 'products'}],
       business_key={'field': 'products', 'item_fields': ['id']})
    bounded = spec.model_dump(mode='json')
    bounded['coverage']['scope'] = 'bounded'
    assert MonitorSpec.model_validate(bounded).coverage.scope == 'bounded'
    bounded['fields'][0]['allow_empty'] = False
    with pytest.raises(ValidationError):
        MonitorSpec.model_validate(bounded)
    foreign = spec.model_dump(mode='json')
    foreign['change_rules']['rules'][0]['field'] = 'related'
    with pytest.raises(ValidationError):
        MonitorSpec.model_validate(foreign)


def test_list_removal_can_end_in_an_empty_observed_list():
    spec = make_spec([
        {'name': 'products', 'type': 'list', 'semantic': 'Products', 'selector': '.product',
         'item_fields': [{'name': 'id', 'type': 'text', 'semantic': 'Stable ID', 'selector': '.id'}],
         'allow_empty': True},
    ], [{'type': 'list_removed', 'field': 'products'}],
       business_key={'field': 'products', 'item_fields': ['id']})
    a = {'id': 'A'}
    b = {'id': 'B'}
    result = evaluate_rules(spec, {'products': [a, b]}, {'products': []}, {})
    assert result['triggered'] is True
    assert result['event_type'] == 'list_changed'
    assert result['differences'][0]['items'] == [a, b]



def test_list_numeric_formatting_is_not_a_business_update():
    spec = make_spec([{'name': 'products', 'type': 'list', 'semantic': 'Products', 'selector': '.row',
        'item_fields': [
            {'name': 'id', 'type': 'text', 'semantic': 'Identity', 'selector': '.id'},
            {'name': 'price', 'type': 'money', 'semantic': 'Price', 'selector': '.price',
             'normalize': {'decimal_separator': '.', 'currency': 'USD'}},
            {'name': 'quantity', 'type': 'number', 'semantic': 'Quantity', 'selector': '.qty',
             'normalize': {'decimal_separator': '.'}}]}],
        [{'type': 'list_updated', 'field': 'products', 'watch_fields': ['price', 'quantity']}],
        business_key={'field': 'products', 'item_fields': ['id']})
    before = {'products': [{'id': 'A', 'price': {'amount': '12.50', 'currency': 'USD'}, 'quantity': '2.0'}]}
    same = {'products': [{'id': 'A', 'price': {'amount': '12.5', 'currency': 'USD'}, 'quantity': '2'}]}
    assert not evaluate_rules(spec, before, same, {})['triggered']
    changed = {'products': [{'id': 'A', 'price': {'amount': '12.6', 'currency': 'USD'}, 'quantity': '2'}]}
    result = evaluate_rules(spec, same, changed, {})
    assert result['triggered']
    assert result['differences'][0]['items'][0]['fields'] == ['price']


def test_persistent_transition_triggers_even_with_change_rules_present():
    spec = make_spec([
        {'name': 'price', 'type': 'number', 'semantic': 'Current price', 'selector': '.price',
         'normalize': {'decimal_separator': '.'}},
        {'name': 'title', 'type': 'text', 'semantic': 'Title', 'selector': '.title'},
    ], [
        {'type': 'threshold', 'field': 'price', 'operator': 'gte', 'value': '100'},
        {'type': 'text_changed', 'field': 'title'},
    ])
    initial = evaluate_rules(spec, None, {'price': '90', 'title': 'A'}, {})
    assert initial['rule_state']['persistent_aggregate'] is False
    crossed = evaluate_rules(spec, {'price': '90', 'title': 'A'},
                             {'price': '100', 'title': 'A'}, initial['rule_state'])
    assert crossed['triggered'] is True
    assert [item['type'] for item in crossed['differences']] == ['threshold']
    assert crossed['differences'][0]['before'] == '90'


def test_persistent_transition_under_all_mode_needs_every_rule():
    spec = make_spec([
        {'name': 'price', 'type': 'number', 'semantic': 'Current price', 'selector': '.price',
         'normalize': {'decimal_separator': '.'}},
        {'name': 'title', 'type': 'text', 'semantic': 'Title', 'selector': '.title'},
    ], [
        {'type': 'threshold', 'field': 'price', 'operator': 'gte', 'value': '100'},
        {'type': 'keyword_present', 'field': 'title', 'keyword': '限时'},
    ], mode='all')
    initial = evaluate_rules(spec, None, {'price': '90', 'title': '常规'}, {})
    half = evaluate_rules(spec, {'price': '90', 'title': '常规'},
                          {'price': '120', 'title': '常规'}, initial['rule_state'])
    assert half['triggered'] is False
    both = evaluate_rules(spec, {'price': '120', 'title': '常规'},
                          {'price': '120', 'title': '限时 促销'}, half['rule_state'])
    assert both['triggered'] is True
    assert both['rule_state']['persistent_aggregate'] is True


def test_list_rule_payload_carries_only_the_delta():
    rows = [{'name': 'id', 'type': 'text', 'semantic': 'ID', 'selector': '.id'}]
    spec = make_spec([
        {'name': 'products', 'type': 'list', 'semantic': 'Products', 'selector': '.product',
         'item_fields': rows},
    ], [{'type': 'list_added', 'field': 'products'}],
       business_key={'field': 'products', 'item_fields': ['id']})
    before = {'products': [{'id': f'row-{index}', 'payload': 'x' * 200} for index in range(500)]}
    after = {'products': before['products'] + [{'id': 'row-new', 'payload': 'new'}]}
    state = evaluate_rules(spec, None, before, {})
    result = evaluate_rules(spec, before, after, state['rule_state'])
    difference = result['differences'][0]
    assert difference['before'] is None and difference['after'] is None
    assert difference['items'] == [{'id': 'row-new', 'payload': 'new'}]
    assert len(json.dumps(result, ensure_ascii=False)) < 1000


@pytest.mark.parametrize('kind,before,after', [
    ('date', '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z'),
    ('boolean', False, True),
    ('url', 'https://example.com/old', 'https://example.com/new'),
])
def test_value_changed_supports_only_typed_scalar_changes(kind, before, after):
    spec = scalar_spec(kind, {'type': 'value_changed'})
    initial = evaluate_rules(spec, None, {'value': before}, {})
    changed = evaluate_rules(spec, {'value': before}, {'value': after}, initial['rule_state'])
    unchanged = evaluate_rules(spec, {'value': after}, {'value': after}, changed['rule_state'])
    assert changed['triggered'] is True
    assert unchanged['triggered'] is False


@pytest.mark.parametrize('kind', ['text', 'number'])
def test_value_changed_rejects_text_and_numeric_fields(kind):
    with pytest.raises(ValidationError):
        scalar_spec(kind, {'type': 'value_changed'})


@pytest.mark.parametrize('kind,before,after,pattern', [
    ('text', 'pending', 'ready', '^ready$'),
    ('date', '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z', '^2026-01-02T.*Z$'),
    ('boolean', False, True, '^true$'),
    ('url', 'https://example.com/draft', 'https://example.com/released', '/released$'),
])
def test_regex_match_uses_deterministic_scalar_text_and_persistent_transitions(
        kind, before, after, pattern):
    spec = scalar_spec(kind, {'type': 'regex_match', 'pattern': pattern})
    initial = evaluate_rules(spec, None, {'value': before}, {})
    matched = evaluate_rules(spec, {'value': before}, {'value': after}, initial['rule_state'])
    sustained = evaluate_rules(spec, {'value': after}, {'value': after}, matched['rule_state'])
    assert matched['triggered'] is True
    assert matched['rule_state']['predicates'] == {'0': True}
    assert sustained['triggered'] is False


def test_regex_schema_precompiles_and_rejects_invalid_patterns_and_types():
    with pytest.raises(ValidationError):
        scalar_spec('text', {'type': 'regex_match', 'pattern': '[unclosed'})
    with pytest.raises(ValidationError):
        scalar_spec('number', {'type': 'regex_match', 'pattern': '.*'})


def test_pathological_regex_times_out_as_a_nonmatching_warning():
    spec = scalar_spec('text', {'type': 'regex_match', 'pattern': '(a+)+$'})
    result = evaluate_rules(spec, {'value': 'short'}, {'value': 'a' * 100_000 + '!'}, {})
    assert result['triggered'] is False
    assert result['warnings'] == [{'code': 'rule_timeout', 'rule_index': 0,
                                  'field': 'value', 'reason': 'regex_timeout'}]


def test_consecutive_hits_default_one_preserves_legacy_state_and_behavior():
    spec = scalar_spec('boolean', {'type': 'value_changed'})
    legacy_state = {'predicates': {}, 'aggregate': True, 'persistent_aggregate': False}
    result = evaluate_rules(spec, {'value': False}, {'value': True}, legacy_state)
    assert result['triggered'] is True
    assert 'confirmation' not in result['rule_state']


def test_consecutive_persistent_hits_confirm_jitter_and_reset_after_firing():
    spec = scalar_spec('text', {'type': 'regex_match', 'pattern': '^ready'},
                       consecutive_hits=2)
    initial = evaluate_rules(spec, None, {'value': 'pending'}, {})
    first = evaluate_rules(spec, {'value': 'pending'}, {'value': 'ready'}, initial['rule_state'])
    assert first['triggered'] is False
    assert first['rule_state']['confirmation']['count'] == 1
    assert first['rule_state']['confirmation']['rule_signature']
    assert first['rule_state']['confirmation']['value_fingerprint']

    jitter = evaluate_rules(spec, {'value': 'ready'}, {'value': 'ready now'},
                            first['rule_state'])
    assert jitter['triggered'] is False
    assert jitter['rule_state']['confirmation']['count'] == 1
    confirmed = evaluate_rules(spec, {'value': 'ready now'}, {'value': 'ready now'},
                               jitter['rule_state'])
    assert confirmed['triggered'] is True
    assert 'confirmation' not in confirmed['rule_state']
    sustained = evaluate_rules(spec, {'value': 'ready now'}, {'value': 'ready now'},
                               confirmed['rule_state'])
    assert sustained['triggered'] is False
    assert 'confirmation' not in sustained['rule_state']


def test_consecutive_hits_reset_when_the_matching_rule_set_changes():
    text_fields = [
        {'name': 'first', 'type': 'text', 'semantic': 'First', 'selector': '.first'},
        {'name': 'second', 'type': 'text', 'semantic': 'Second', 'selector': '.second'},
    ]
    spec = make_spec(text_fields, [
        {'type': 'regex_match', 'field': 'first', 'pattern': '^yes$'},
        {'type': 'regex_match', 'field': 'second', 'pattern': '^yes$'},
    ], consecutive_hits=2)
    initial = evaluate_rules(spec, None, {'first': 'no', 'second': 'no'}, {})
    first = evaluate_rules(spec, {'first': 'no', 'second': 'no'},
                           {'first': 'yes', 'second': 'no'}, initial['rule_state'])
    changed_rules = evaluate_rules(spec, {'first': 'no', 'second': 'no'},
                                   {'first': 'yes', 'second': 'yes'}, first['rule_state'])
    assert changed_rules['triggered'] is False
    assert changed_rules['rule_state']['confirmation']['count'] == 1
    assert (changed_rules['rule_state']['confirmation']['rule_signature']
            != first['rule_state']['confirmation']['rule_signature'])


def test_consecutive_change_hits_require_the_same_rule_and_value():
    spec = scalar_spec('date', {'type': 'value_changed'}, consecutive_hits=2)
    baseline = '2026-01-01T00:00:00Z'
    first_value = '2026-01-02T00:00:00Z'
    jittered_value = '2026-01-03T00:00:00Z'
    initial = evaluate_rules(spec, None, {'value': baseline}, {})
    first = evaluate_rules(spec, {'value': baseline}, {'value': first_value}, initial['rule_state'])
    assert first['triggered'] is False and first['rule_state']['confirmation']['count'] == 1

    # Production retains the original baseline while a candidate is pending.
    confirmed = evaluate_rules(spec, {'value': baseline}, {'value': first_value},
                               first['rule_state'])
    assert confirmed['triggered'] is True
    assert confirmed['differences'][0]['before'] == baseline
    assert 'confirmation' not in confirmed['rule_state']

    jitter = evaluate_rules(spec, {'value': baseline}, {'value': jittered_value},
                            first['rule_state'])
    assert jitter['triggered'] is False
    assert jitter['rule_state']['confirmation']['count'] == 1
    assert (jitter['rule_state']['confirmation']['value_fingerprint']
            != first['rule_state']['confirmation']['value_fingerprint'])
    returned = evaluate_rules(spec, {'value': baseline}, {'value': baseline}, first['rule_state'])
    assert returned['triggered'] is False
    assert 'confirmation' not in returned['rule_state']


@pytest.mark.parametrize('hits', [0, 11, True, 1.5])
def test_consecutive_hits_is_a_bounded_strict_integer(hits):
    with pytest.raises(ValidationError):
        scalar_spec('text', {'type': 'regex_match', 'pattern': 'ready'}, consecutive_hits=hits)
