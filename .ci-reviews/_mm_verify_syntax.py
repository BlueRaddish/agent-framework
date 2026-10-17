"""Compile the actual URI snippet with a real supported interpreter."""
import argparse,ast,json,sys,textwrap
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--mode',required=True,choices=['example','baseline']);a=p.parse_args()
    assert sys.version_info[:2] in ((3,10),(3,11))
    source=Path(a.source).resolve()/'python/packages/core/agent_framework/_types.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Content')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='from_uri')
    doc=ast.get_docstring(method);assert doc and doc.count('.. code-block:: python')==1
    code=textwrap.dedent(doc.split('.. code-block:: python',1)[1]).strip();assert code
    if a.mode=='baseline':
        try:compile(code,'Content.from_uri actual baseline','exec')
        except SyntaxError as e:assert 'string' in str(e) and e.lineno>=10
        else:raise AssertionError('The real old interpreter unexpectedly accepted multiline f-string')
    else:compile(code,'Content.from_uri actual corrected example','exec')
    print('ACTUAL_SYNTAX_CHECK='+json.dumps({'python':sys.version,'mode':a.mode,'passed':True,'source':str(source)}))

if __name__=='__main__':main()
