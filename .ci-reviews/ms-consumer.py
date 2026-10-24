"""Public media detection after an actual serialized Message/Content roundtrip."""
import base64,json
import pytest
from agent_framework import Content,Message,detect_media_type_from_base64
from agent_framework._types import _get_data_bytes,_get_data_bytes_as_str

MEDIA=[('image/png',b'\x89PNG\r\n\x1a\n\xfb\xef\xff'),('image/jpeg',b'\xff\xd8\xff\xfb\xef\xff'),
 ('image/gif',b'GIF89a\xfb\xef\xff'),('application/pdf',b'%PDF-1.7\n\xfb\xef\xff')]

@pytest.mark.parametrize('media,raw',MEDIA)
@pytest.mark.parametrize('escape',['all','mixed'])
def test_serialized_message_escaped_uri_has_original_bytes(media,raw,escape):
 payload=base64.b64encode(raw).decode()
 encoded=''.join('%'+format(ord(c),'02x') for c in payload) if escape=='all' else '%'+format(ord(payload[0]),'02X')+payload[1:].replace('/','%2F').replace('=','%3D')
 uri='data:'+media+';name=kept%2Fmetadata;base64,'+encoded
 message=Message(role='user',contents=[Content.from_uri(uri=uri)])
 restored=Message.from_dict(json.loads(json.dumps(message.to_dict())))
 content=restored.contents[0]
 assert content.uri==uri and content.media_type==media
 assert detect_media_type_from_base64(data_uri=content.uri)==media
 assert _get_data_bytes_as_str(content)==payload
 assert _get_data_bytes(content)==raw
 assert Content.from_dict(json.loads(json.dumps(content.to_dict()))).uri==uri

@pytest.mark.parametrize('media,raw',MEDIA)
def test_literal_message_roundtrip_control(media,raw):
 uri='data:'+media+';base64,'+base64.b64encode(raw).decode()
 content=Message.from_dict(Message(role='user',contents=[Content.from_uri(uri=uri)]).to_dict()).contents[0]
 assert detect_media_type_from_base64(data_uri=content.uri)==media
 assert _get_data_bytes(content)==raw and content.uri==uri
