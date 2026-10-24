"""Public SQLite return filtering and retained-storage isolation, with real FTS5."""
import json
import sqlite3
from google.adk.events import Event
from google.adk.memory import SqliteMemoryService
from google.genai import types
import pytest

@pytest.mark.parametrize('fts', ['off', 'on'])
@pytest.mark.parametrize('kind', ['mixed', 'legacy-all-thought', 'visible-control'])
async def test_public_memory_boundary(tmp_path, fts, kind):
    path = tmp_path / 'memory.db'
    service = SqliteMemoryService(path, fts=fts)
    visible = types.Part(text='saffron tea', thought=False)
    image = types.Part.from_bytes(data=b'visible', mime_type='image/png')
    hidden = types.Part(text='synthetic hidden', thought=True)
    parts = [visible, hidden, image] if kind == 'mixed' else [visible, image]
    original = Event(id='event', author='assistant', content=types.Content(role='model', parts=parts))
    snapshot = original.model_dump_json()
    try:
        await service.add_events_to_memory(app_name='app', user_id='user', session_id='history', events=[original])
        if kind == 'legacy-all-thought':
            with sqlite3.connect(path) as db:
                db.execute('UPDATE memory_events SET content_json=?', (types.Content(role='model', parts=[hidden]).model_dump_json(),))
                db.commit()
        with sqlite3.connect(path) as db:
            before = db.execute('SELECT content_json FROM memory_events').fetchone()[0]
        response = await service.search_memory(app_name='app', user_id='user', query='saffron')
        assert len(response.memories) == 1
        item = response.memories[0]
        assert item.content.role == 'model'
        assert item.custom_metadata == {'session_id': 'history', 'event_id': 'event'}
        assert item.content.parts == ([] if kind == 'legacy-all-thought' else [visible, image])
        serialized = response.model_dump_json()
        assert 'synthetic hidden' not in serialized
        item.content.parts.append(types.Part(text='caller mutation'))
        second = await service.search_memory(app_name='app', user_id='user', query='saffron')
        assert 'caller mutation' not in second.model_dump_json()
        assert original.model_dump_json() == snapshot
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT content_json FROM memory_events').fetchone()[0] == before
        assert not (await service.search_memory(app_name='app', user_id='other', query='saffron')).memories
    finally:
        await service.close()
