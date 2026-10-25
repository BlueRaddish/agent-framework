"""Real persisted-profile public readers; UTF-8 and ASCII controls, no locale patches."""
import json
from pathlib import Path
from uuid import uuid4
import gc
import pytest
from openhands.sdk import LLM, Agent, Conversation
from openhands.sdk.llm.llm_profile_store import LLMProfileStore
from openhands.sdk.profiles import AgentProfileStore, OpenHandsAgentProfile
from openhands.sdk.tool import client_tool as ct, registry as reg
from openhands.sdk.tool.client_tool import ClientToolSpec
from openhands.sdk.utils.models import clear_subclass_cache

@pytest.fixture(autouse=True)
def collect_types():
    yield
    gc.collect()
    clear_subclass_cache()

@pytest.mark.parametrize('unicode', [False, True])
@pytest.mark.parametrize('reader', ['agent-load', 'agent-rename', 'agent-ref', 'agent-summary', 'llm-summary', 'llm-load', 'llm-store-load', 'conversation-resume'])
def test_persisted_reader(tmp_path, unicode, reader):
    value = 'caf\u00e9' if unicode else 'plain'
    if reader.startswith('agent-'):
        store = AgentProfileStore(tmp_path / 'agents')
        profile = OpenHandsAgentProfile(name='profile', llm_profile_ref=value, system_message_suffix=value)
        store.save(profile)
        path = store.base_dir / 'profile.json'
        # Profile writers currently use ASCII escapes: this deliberately seeds
        # valid UTF-8 payloads, as issue6108's latent reader criteria request.
        path.write_bytes(json.dumps(profile.model_dump(mode='json'), ensure_ascii=False).encode('utf-8'))
        if reader == 'agent-load': assert store.load('profile').system_message_suffix == value
        if reader == 'agent-summary': assert store.list_summaries()[0]['llm_profile_ref'] == value
        if reader == 'agent-rename':
            store.rename('profile', 'renamed')
            assert store.load('renamed').system_message_suffix == value
        if reader == 'agent-ref':
            store.set_llm_profile_ref('profile', 'changed')
            assert store.load('profile').system_message_suffix == value
        return
    if reader.startswith('llm-'):
        store = LLMProfileStore(base_dir=tmp_path / 'llms')
        model = LLM(model='gpt-4o', usage_id='offline-review', base_url='https://example.invalid/' + value)
        store.save('profile', model)
        path = store.base_dir / 'profile.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        path.write_bytes(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        if reader == 'llm-summary': result = store.list_summaries()[0]['base_url']
        elif reader == 'llm-load': result = LLM.load_from_json(str(path)).base_url
        else: result = store.load('profile').base_url
        assert result == model.base_url
        return
    cid = uuid4()
    persist = tmp_path / 'persist'
    workspace = tmp_path / 'workspace'
    name = 'oct23_review_client_tool_' + str(unicode)
    def agent(): return Agent(llm=LLM(model='gpt-4o', usage_id='offline-review'), tools=[])
    created = Conversation(agent=agent(), workspace=str(workspace), persistence_dir=str(persist), conversation_id=cid,
                           client_tools=[ClientToolSpec(name=name, description=value, parameters={'type': 'object', 'properties': {}})], delete_on_close=False)
    created.close()
    del created
    ct._client_action_types.clear()
    ct._client_action_schemas.clear()
    for mapping in [reg._REG, reg._USABILITY_REG, reg._MODULE_QUALNAMES]: mapping.pop(name, None)
    gc.collect()
    clear_subclass_cache()
    resumed = Conversation(agent=agent(), workspace=str(workspace), persistence_dir=str(persist), conversation_id=cid, delete_on_close=False)
    try:
        tools = [tool for tool in resumed.agent.tools if tool.name == name]
        assert len(tools) == 1
        assert tools[0].params['spec']['description'] == value
    finally:
        resumed.close()
