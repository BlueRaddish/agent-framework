"""Public Agent.run with a deterministic in-process chat client; no provider calls."""
import pytest
from agent_framework import (
    Agent, BaseChatClient, ChatResponse, Content, FunctionInvocationLayer,
    FunctionMiddleware, FunctionTool, Message, tool,
)

class LocalClient(FunctionInvocationLayer, BaseChatClient):
    def __init__(self, arguments):
        super().__init__()
        self.arguments = arguments
        self.turns = 0
        self.tool_results = []

    def _inner_get_response(self, *, messages, stream, options, **kwargs):
        assert not stream
        async def respond():
            self.turns += 1
            assert self.turns <= 2, 'Unexpected extra agent turn'
            if self.turns == 1:
                return ChatResponse(messages=[Message(role='assistant', contents=[
                    Content.from_function_call(call_id='call-1', name='target', arguments=self.arguments),
                ])])
            self.tool_results = [c for m in messages for c in m.contents if c.type == 'function_result']
            return ChatResponse(messages=[Message(role='assistant', text='done')])
        return respond()

class PassThrough(FunctionMiddleware):
    async def process(self, context, call_next):
        await call_next()

class Repair(FunctionMiddleware):
    async def process(self, context, call_next):
        context.arguments = {}
        await call_next()

async def invoke(arguments, *, kind='schema', middleware=None):
    calls = []
    if kind == 'schema':
        async def record(**kwargs):
            calls.append(kwargs)
            return 'called'
        target = FunctionTool(name='target', description='Local recorder', func=record,
                              input_model={'type':'object','properties':{}})
    else:
        @tool(name='target')
        def target():
            calls.append({})
            return 'called'
    client = LocalClient(arguments)
    agent = Agent(client=client, tools=[target], middleware=[] if middleware is None else [middleware])
    response = await agent.run('run the local target')
    assert response.text == 'done' and client.turns == 2
    assert len(client.tool_results) == 1
    return calls, client.tool_results[0]

@pytest.mark.asyncio
@pytest.mark.parametrize(('kind','middleware'), [('schema',None),('schema',PassThrough()),('zero',None)])
async def test_null_payload_is_rejected_before_tool_runs(kind, middleware):
    calls, result = await invoke('null', kind=kind, middleware=middleware)
    assert calls == [], f'Tool unexpectedly executed: {calls!r}'
    assert 'not a JSON object' in str(result.exception)

@pytest.mark.asyncio
async def test_array_payload_control_is_rejected():
    calls, result = await invoke('[1, 2]')
    assert calls == [] and 'not a JSON object' in str(result.exception)

@pytest.mark.asyncio
async def test_valid_object_control_runs():
    calls, result = await invoke('{}')
    assert calls == [{}] and result.exception is None

@pytest.mark.asyncio
async def test_middleware_repair_control_runs():
    calls, result = await invoke('null', middleware=Repair())
    assert calls == [{}] and result.exception is None
