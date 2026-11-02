"""Captured API responses are bounded evidence, never a bulk download."""
import json

from webmonitor.collection.network import MAX_REQUEST_BODY, MAX_SAMPLE, network_candidate

BODY = json.dumps({'code': 200, 'data': {'list': [{'id': 1}, {'id': 2}], 'total': 2}}).encode()


def test_candidate_filters_headers_and_summarizes_payload():
    candidate = network_candidate(
        method='GET', url='https://api.example.com/items', status=200,
        content_type='application/json',
        headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json',
                 'Cookie': 'session=secret', 'X-Trace': '1'},
        request_body=None, body=BODY)
    assert candidate == {
        'method': 'GET',
        'url': 'https://api.example.com/items',
        'status': 200,
        'content_type': 'application/json',
        'headers': {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'},
        'request_body': None,
        'sample': BODY.decode(),
        'summary': {'root': 'object', 'keys': ['code', 'data'],
                    'lists': [{'path': 'data.list', 'count': 2, 'item_keys': ['id']}],
                    'pagination': [{'path': 'data.total', 'value': 2}]},
        'size': len(BODY),
    }


def test_candidate_truncates_request_body_and_sample():
    long_body = json.dumps({'data': {'list': [{'id': 'x' * 200}]}, 'pad': 'y' * 20000}).encode()
    candidate = network_candidate(
        method='POST', url='https://api.example.com/search', status=200,
        content_type='application/json', headers={},
        request_body='{"q":"' + 'z' * 20000 + '"}', body=long_body)
    assert len(candidate['request_body']) == MAX_REQUEST_BODY
    assert len(candidate['sample']) == MAX_SAMPLE
    assert candidate['size'] == len(long_body)
    assert candidate['summary']['lists'][0]['path'] == 'data.list'
