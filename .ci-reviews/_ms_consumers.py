"""Run both repaired examples and the existing URI example via the real public API."""
import argparse,base64,contextlib,inspect,io,json,textwrap
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--mode',choices=['baseline','example'],required=True);a=p.parse_args()
from agent_framework import Content
from agent_framework.exceptions import ContentError
import agent_framework._types as types
assert Path(types.__file__).resolve()==Path(a.source).resolve()/'python/packages/core/agent_framework/_types.py'
signature=b'\x89PNG\r\n\x1a\n'
def code(method):
    d=inspect.getdoc(getattr(Content,method));assert d and 'Examples:' in d
    return textwrap.dedent(d.split('Examples:',1)[1].split('.. code-block:: python',1)[1]).strip()
def execute(method):
    n={};out=io.StringIO()
    with contextlib.redirect_stdout(out):exec(compile(code(method),'actual Content.'+method+' example','exec'),n)
    return n,out.getvalue()
# Positive public controls prove real package initialization and both data modes.
assert Content.from_data(signature,media_type='image/png').type=='data'
image=Content.from_uri('data:image/png;base64,iVBORw0KGgo=')
assert image.has_top_level_media_type('image') and not image.has_top_level_media_type('audio')
assert Content.from_uri('https://example.com/image.png',media_type='image/png').type=='uri'
# The already-published URI example remains an unchanged consuming control.
uri,_=execute('from_uri');assert uri['content'].type=='data'
failures=[]
if a.mode=='baseline':
    for method,error,needle in [('from_data',ValueError,'Invalid base64 data'),('has_top_level_media_type',ContentError,'Failed to decode base64 data')]:
        try:execute(method)
        except error as value:
            assert needle in str(value);failures.append({'method':method,'error_type':type(value).__name__,'message':str(value)})
        else:raise AssertionError('Original documented invalid base64 did not fail: '+method)
    assert len(failures)==2
else:
    data,_=execute('from_data');assert data['content'].type=='data' and data['content'].media_type=='image/png'
    assert data['image_bytes']==signature and data['base64_string']=='iVBORw0KGgo='
    image,out=execute('has_top_level_media_type');assert out=='True\nFalse\n'
    assert base64.b64decode(image['image'].uri.split(',',1)[1],validate=True)==signature
    for method in ['from_data','from_uri','has_top_level_media_type']:
        doc=inspect.getdoc(getattr(Content,method));assert 'iVBORw0KGgo...' not in doc and 'base64,abc123' not in doc
print('OCT17E_MS_CONSUMER='+json.dumps({'state':'passed','mode':a.mode,'origin':types.__file__,'genuine_baseline_failures':failures,'normal_control':'real binary/data/external URI modes and existing complete URI example'}))
