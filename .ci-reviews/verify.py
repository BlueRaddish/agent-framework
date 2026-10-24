"""Frozen review-only consumers; no source commit, API or remote write path."""
import argparse,base64,json,sys
from pathlib import Path
from _mm_common import run,junit,sha
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--scope',choices=['ms','ml'],required=True);a=p.parse_args();assert a.scope=='ml'
v=Path(__file__).resolve().parent;all_spec=json.loads((v/'spec.json').read_text());s=all_spec['sources'][a.scope]
c=Path(a.source).resolve();sdk=c/'python' if a.scope=='ms' else c;proof=c.parent/('proof-'+a.scope);proof.mkdir()
record={'state':'pending','scope':a.scope,'head':s['head'],'comparison_base':s['comparison_base'],'personal_verification_claimed':False,'source_writes':[]}
def git(*args):return run(['git',*args],c)
def exact():
 assert git('rev-parse','HEAD').decode().strip()==s['head']
 assert not git('status','--porcelain','--untracked-files=no').strip()
 assert {n:sha((c/n).read_bytes())for n in s['source_sha256']}==s['source_sha256']
 assert {n:sha((c/n).read_bytes())for n in s['config_sha256']}==s['config_sha256']
def tests(label,args,failures=0,count=None):
 run(['uv','run','--python','3.11','--with','polars>=1','--frozen','--no-sync','pytest',*args,'-q','--junitxml='+str(proof/(label+'.xml'))],sdk,expect=1 if failures else 0)
 return junit(proof/(label+'.xml'),failures=failures,tests=count)
try:
 exact()
 if a.scope=='ms':run(['uv','run','--frozen','poe','install'],sdk)
 else:run(['uv','sync','--locked','--group','dev','--python','3.11'],c)
 exact()
 module='agent_framework._types' if a.scope=='ms' else 'mlflow.tracking.client'
 target=s['production'][0]
 code='import importlib,json,sys;from pathlib import Path;m=importlib.import_module(sys.argv[1]);p=Path(m.__file__).resolve();assert p==Path(sys.argv[2]).resolve();print(json.dumps(dict(python=sys.version,origin=str(p))))'
 record['doctor']=run(['uv','run','--python','3.11','--frozen','--no-sync','python','-c',code,module,str(c/target)],sdk).decode()
 record['quality_only']=True
 if a.scope=='ms':
  record['owners']=tests('owners',['packages/core/tests/core/test_types.py'])
  run(['uv','run','--frozen','poe','prek-install'],sdk)
  command=['uv','run','--frozen','--group','tool-hooks','prek','run','--files',*[n[len('python/'):]for n in s['files']]]
  try:output=run(command,sdk);record['normal_scoped_hooks_passed']=True;record['hook_skips']=output.decode().count('Skipped')
  finally:record['post_hook_diff_base64']=base64.b64encode(git('diff','--full-index','--binary')).decode()
 else:
  record['owners']=tests('owners',['tests/tracking/test_tracking.py','tests/tracking/fluent/test_fluent.py','-k','load_table or log_table or search_runs'])
  env={'UV_PROJECT_ENVIRONMENT':str(c.parent/'hook-env')}
  for command in [['uv','run','--only-group','lint','pre-commit','install','--install-hooks','--hook-type','pre-commit','--hook-type','prepare-commit-msg'],['uv','run','--only-group','lint','pre-commit','run','install-bin','-a','-v']]:run(command,c,extra_env=env)
  try:output=run(['uv','run','--only-group','lint','pre-commit','run','--files',*s['files']],c,extra_env=env);record['normal_scoped_hooks_passed']=True;record['hook_skips']=output.decode().count('Skipped')
  finally:record['post_hook_diff_base64']=base64.b64encode(git('diff','--full-index','--binary')).decode()
 exact();record['state']='passed actual owning tests and normal scoped hooks; independent red/green retained from original job'
except BaseException as error:record.update(state='failed_or_partial',error=repr(error));raise
finally:print('OCT23_MM_RESULT='+json.dumps(record),flush=True)
