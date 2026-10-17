"""Run the complete URI docstring in its real public package."""
import argparse,ast,base64,inspect,json,textwrap
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--scope',required=True,choices=['ms-oct17-uri']);p.add_argument('--source',required=True);p.add_argument('--mode',required=True,choices=['example','baseline','normal-control']);a=p.parse_args()
    from agent_framework import Content,detect_media_type_from_base64
    import agent_framework._types as types
    assert Path(types.__file__).resolve()==Path(a.source).resolve()/'python/packages/core/agent_framework/_types.py'
    if a.mode=='normal-control':
        assert Content.from_uri('https://example.com/image.png',media_type='image/png').type=='uri'
        c=Content.from_uri('data:image/png;base64,iVBORw0KGgo=')
        assert c.type=='data' and c.media_type=='image/png' and base64.b64decode(c.uri.split(',',1)[1],validate=True)==b'\x89PNG\r\n\x1a\n'
    else:
        doc=inspect.getdoc(Content.from_uri);assert doc and doc.count('.. code-block:: python')==1
        code=textwrap.dedent(doc.split('.. code-block:: python',1)[1]).strip();assert code
        if a.mode=='baseline':
            for version in [(3,10),(3,11)]:
                try:ast.parse(code,feature_version=version)
                except SyntaxError:pass
                else:raise AssertionError('Expected unsupported multiline f-string grammar')
            try:exec(compile(code,'Content.from_uri actual baseline','exec'),{})
            except NameError as e:assert "detect_media_type_from_base64" in str(e)
            else:raise AssertionError('Baseline did not fail at missing public import')
            try:exec(compile(code,'Content.from_uri actual baseline dependency diagnostic','exec'),{'detect_media_type_from_base64':detect_media_type_from_base64})
            except ValueError as e:assert 'Invalid base64 data' in str(e)
            else:raise AssertionError('Invalid placeholder base64 was not rejected')
        else:
            for version in [(3,10),(3,11)]:ast.parse(code,feature_version=version)
            n={};exec(compile(code,'Content.from_uri actual fixed example','exec'),n)
            assert n['content'].type=='data' and n['content'].media_type=='image/png'
            assert n['content'].uri=='data:image/png;base64,iVBORw0KGgo='
            assert base64.b64decode(n['content'].uri.split(',',1)[1],validate=True)==b'\x89PNG\r\n\x1a\n'
    print('ACTUAL_CONSUMER_CHECK='+json.dumps({'scope_id':a.scope,'mode':a.mode,'passed':True,'origin':types.__file__}))

if __name__=='__main__':main()
