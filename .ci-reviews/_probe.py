"""Exercise the public embedding API through an in-memory HTTP transport."""
import asyncio
import base64
import json
import struct
import httpx
import pytest
from openai import AsyncOpenAI
from agent_framework_openai import OpenAIEmbeddingClient


def invoke(payloads, encoding='base64', values=None):
    requests = []
    def serve(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            'object': 'list', 'model': 'test-model',
            'data': [{'object': 'embedding', 'index': index, 'embedding': value}
                     for index, value in reversed(list(enumerate(payloads)))],
            'usage': {'prompt_tokens': 3, 'total_tokens': 3}})
    async def go():
        async with AsyncOpenAI(api_key='test-only', base_url='https://example.invalid/v1',
                               http_client=httpx.AsyncClient(transport=httpx.MockTransport(serve))) as sdk:
            client = OpenAIEmbeddingClient(model='test-model', async_client=sdk)
            options = {'encoding_format': encoding}
            result = await client.get_embeddings(values if values is not None else ['text'] * len(payloads),
                                                 options=options)
            assert result.options is options
            return result
    result = asyncio.run(go())
    if values != []:
        assert len(requests) == 1
        assert requests[0]['encoding_format'] == encoding and requests[0]['model'] == 'test-model'
        assert result.usage == {'input_token_count': 3, 'total_token_count': 3}
    else:
        assert requests == []
    return result


@pytest.mark.parametrize('length', [1, 2, 3, 5, 6, 7, 9])
def test_misaligned_response_names_actual_input_index_and_byte_count(length):
    good = base64.b64encode(struct.pack('<f', 0.5)).decode()
    bad = base64.b64encode(b'\0' * length).decode()
    with pytest.raises(ValueError, match=f'input index 1 decoded to {length} bytes, which cannot be split'):
        invoke([good, bad])


@pytest.mark.parametrize('floats', [[], [0.5], [0.5, -1.25]])
def test_aligned_base64_preserves_vectors_order_dimensions_and_usage(floats):
    encoded = base64.b64encode(struct.pack(f'<{len(floats)}f', *floats)).decode()
    result = invoke([encoded, base64.b64encode(struct.pack('<f', 2.0)).decode()])
    assert [x.vector for x in result] == [floats, [2.0]]
    assert [x.dimensions for x in result] == [len(floats), 1]
    assert all(x.model == 'test-model' for x in result)


def test_float_encoding_remains_unchanged():
    assert [x.vector for x in invoke([[0.5], [2.0]], encoding='float')] == [[0.5], [2.0]]


def test_empty_input_avoids_sdk_request():
    assert len(invoke([], values=[])) == 0
