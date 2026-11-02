"""The structural summary is bounded, advisory and never raises."""
from webmonitor.collection.json_extract import json_summary

BODY = {
    'code': 200,
    'data': {
        'total': 8,
        'page': 1,
        'list': [{'id': 1, 'title': 'A', 'tags': [{'name': 't'}]}, {'id': 2, 'title': 'B'}],
        'empty': [],
        'scalars': [1, 2, 3],
    },
}


def test_lists_and_pagination_hints_are_reported_with_paths():
    summary = json_summary(BODY)
    assert summary['root'] == 'object'
    assert summary['keys'][:3] == ['code', 'data']
    assert {'path': 'data.list', 'count': 2, 'item_keys': ['id', 'title', 'tags']} \
        in summary['lists']
    assert {'path': 'data.total', 'value': 8} in summary['pagination']
    assert {'path': 'data.page', 'value': 1} in summary['pagination']
    # Empty and scalar-only lists are not candidates for extraction.
    paths = {item['path'] for item in summary['lists']}
    assert 'data.empty' not in paths and 'data.scalars' not in paths


def test_nested_lists_are_found_but_depth_is_bounded():
    summary = json_summary({'data': {'wrapper': {'list': [{'id': 1}]}}})
    assert 'data.wrapper.list' in {item['path'] for item in summary['lists']}
    # Rows of a list sit deeper than the traversal budget, so their inner lists
    # are not reported; the agent must pick one addressable list instead.
    deep = {'data': {'list': [{'tags': [{'name': 'a'}]}]}}
    paths = {item['path'] for item in json_summary(deep)['lists']}
    assert 'data.list' in paths and 'data.list[0].tags' not in paths


def test_root_array_and_odd_bodies_never_raise():
    summary = json_summary([{'id': 1}])
    assert summary['root'] == 'array' and summary['keys'] == []
    assert json_summary('text')['root'] == 'scalar'
    assert json_summary(None)['lists'] == []
    assert json_summary({'a': {1, 2}})['root'] == 'object'
    huge = {'data': {'list': [{'id': index} for index in range(5000)]}}
    summary = json_summary(huge)
    assert summary['lists'][0]['count'] == 5000
