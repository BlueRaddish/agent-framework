"""Compile the actual final public snippets with the requested real interpreter."""
import argparse,ast,json,textwrap,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',required=True);a=p.parse_args()
assert sys.version_info[:2] in [(3,10),(3,11)]
raw=(Path(a.source)/'python/packages/core/agent_framework/_types.py').read_text()
c=next(n for n in ast.parse(raw).body if isinstance(n,ast.ClassDef) and n.name=='Content')
methods=['from_data','from_uri','has_top_level_media_type']
for method in methods:
    n=next(n for n in c.body if isinstance(n,ast.FunctionDef) and n.name==method)
    d=ast.get_docstring(n);assert d
    code=textwrap.dedent(d.split('Examples:',1)[1].split('.. code-block:: python',1)[1]).strip()
    compile(code,'actual Content.'+method+' example','exec')
print('OCT17E_MS_SYNTAX='+json.dumps({'python':sys.version,'methods':methods,'state':'passed actual final snippet compilation'}))
