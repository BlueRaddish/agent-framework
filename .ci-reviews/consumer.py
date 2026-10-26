"""Drive unchanged sample main() up to its client boundary without model calls."""
import argparse,asyncio,contextlib,json,os,re,runpy
from pathlib import Path
from unittest.mock import patch
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--baseline',action='store_true');a=p.parse_args();c=Path(a.source).resolve();results=[]
class ClientBoundary(Exception):pass
for name in ['file_based_skill','mixed_skills']:
 folder=c/'python/samples/02-agents/skills'/name
 with patch('dotenv.load_dotenv',return_value=False):namespace=runpy.run_path(str(folder/(name+'.py')))
 def capture(**kwargs):raise ClientBoundary(kwargs)
 namespace['main'].__globals__['FoundryChatClient']=capture
 namespace['main'].__globals__['AzureCliCredential']=lambda:None
 readme=(folder/'README.md').read_text(encoding='utf8')
 variables=set(re.findall(r'\b(?:AZURE_OPENAI_MODEL|FOUNDRY_MODEL)\b',readme));assert len(variables)==1
 documented=variables.pop()
 for case,variable,expected in [('readme',documented,'my-custom-deployment'),('explicit-control','FOUNDRY_MODEL','my-custom-deployment'),('default-control',None,'gpt-4o-mini')]:
  env={'FOUNDRY_PROJECT_ENDPOINT':'https://example.services.ai.azure.com/api/projects/example'}
  if variable:env[variable]='my-custom-deployment'
  with patch.dict(os.environ,env,clear=True):
   try:asyncio.run(namespace['main']())
   except ClientBoundary as stop:actual=stop.args[0]
   else:raise AssertionError('Client boundary was not reached')
  assert actual['project_endpoint']==env['FOUNDRY_PROJECT_ENDPOINT']
  results.append({'sample':name,'case':case,'documented_variable':documented,'actual_model':actual['model'],'expected_model':expected,'passed':actual['model']==expected})
failed=[x for x in results if not x['passed']]
assert len(failed)==(2 if a.baseline else 0)
assert all(x['case']=='readme' for x in failed)
print('OCT25B_MS_CONSUMER='+json.dumps({'cases':results,'passed':len(results)-len(failed),'expected_failures':len(failed),'network_or_model_calls':0}),flush=True)
