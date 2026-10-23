"""Execute the complete response class documentation examples through the real SDK."""
import argparse,ast,contextlib,inspect,io,json,sys,textwrap
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--phase',choices=['syntax','baseline','fixed'],required=True);a=p.parse_args()
source=Path(a.source).resolve();raw=(source/'python/packages/core/agent_framework/_types.py').read_text()
tree=ast.parse(raw)
def code(name):
 n=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name==name)
 return textwrap.dedent(ast.get_docstring(n).split('Examples:',1)[1].split('.. code-block:: python',1)[1]).strip()
classes=['ChatResponse','AgentResponse']
if a.phase=='syntax':
 assert sys.version_info[:2] in [(3,10),(3,11)]
 for name in classes:compile(code(name),'actual '+name+' complete example','exec')
 print('OCT22_MS_CONSUMER='+json.dumps({'phase':'syntax','python':sys.version,'classes':classes}));raise SystemExit(0)
import agent_framework._types as types
from agent_framework import ChatResponse,ChatResponseUpdate,AgentResponse,AgentResponseUpdate,Content,Message
assert Path(types.__file__).resolve()==source/'python/packages/core/agent_framework/_types.py'
assert ChatResponse.from_updates([ChatResponseUpdate(contents=[Content.from_text('ok')],role='assistant')]).text=='ok'
assert AgentResponse.from_updates([AgentResponseUpdate(contents=[Content.from_text('ok')],role='assistant',response_id='control')]).response_id=='control'
assert Message.from_json(Message('user',['control']).to_json()).text=='control'
failures=[]
for name in classes:
 ns={};output=io.StringIO()
 try:
  with contextlib.redirect_stdout(output):exec(compile(code(name),'actual '+name+' complete example','exec'),ns)
 except AttributeError as error:
  assert a.phase=='baseline' and 'ellipsis' in str(error).lower(),repr(error)
  failures.append({'class':name,'type':type(error).__name__,'message':str(error)})
 else:
  assert a.phase=='fixed','Original illustrative placeholder unexpectedly runnable'
  expected='The weather is sunny.' if name=='ChatResponse' else 'Task completed successfully.'
  assert ns['response'].text==ns['restored_response'].text==ns['restored_from_json'].text==expected
  if name=='ChatResponse':
   assert ns['restored_response'].model=='gpt-4' and ns['restored_from_json'].model=='gpt-4'
   assert output.getvalue()=='The weather is sunny.\ngpt-4\nThe weather is sunny.\n'
  else:
   assert ns['restored_response'].response_id==ns['restored_from_json'].response_id=='run_123'
   assert output.getvalue()=='Task completed successfully.\n0\nrun_123\nTask completed successfully.\n'
assert len(failures)==(2 if a.phase=='baseline' else 0)
print('OCT22_MS_CONSUMER='+json.dumps({'phase':a.phase,'python':sys.version,'origin':types.__file__,'classes':classes,'genuine_copying_failures':failures,'positive_controls':3,'state':'passed'}))
