"""Execute a frozen bug report, preserving real source and normal project checks."""
import argparse,base64,json
from pathlib import Path
from _mm_common import run,junit,sha
p=argparse.ArgumentParser();p.add_argument('--source',required=True);a=p.parse_args()
v=Path(__file__).resolve().parent;s=json.loads((v/'spec.json').read_text())['source'];c=Path(a.source).resolve();sdk=c/'python';proof=c.parent/'proof-ms';proof.mkdir()
r={'state':'pending','scope':'ms9573','head':s['head'],'personal_verification_claimed':False,'source_writes':[]}
def git(*a):return run(['git',*a],c)
def exact():
 assert git('rev-parse','HEAD').decode().strip()==s['head']
 assert not git('status','--porcelain','--untracked-files=no').strip()
 assert {n:sha((c/n).read_bytes())for n in s['source_sha256']}==s['source_sha256']
 assert {n:sha((c/n).read_bytes())for n in s['config_sha256']}==s['config_sha256']
try:
 exact();run(['uv','run','--frozen','poe','install'],sdk);exact()
 code='import agent_framework,sys,json;from pathlib import Path;p=Path(agent_framework.__file__).resolve();assert p==Path(sys.argv[1]).resolve();print(json.dumps(dict(python=sys.version,origin=str(p))))'
 r['doctor']=run(['uv','run','--python','3.11','--frozen','--no-sync','python','-c',code,str(c/'python/packages/core/agent_framework/__init__.py')],sdk).decode()
 run(['uv','run','--python','3.11','--frozen','--no-sync','pytest',str(v/'ms-consumer.py'),'-q','--junitxml='+str(proof/'consumer.xml')],sdk,expect=1)
 r['consumer']=junit(proof/'consumer.xml',failures=s['expectations']['failures'],tests=s['expectations']['tests'])
 run(['uv','run','--python','3.11','--frozen','--no-sync','pytest','packages/core/tests/core/test_tools.py','-q','--junitxml='+str(proof/'owners.xml')],sdk)
 r['owners']=junit(proof/'owners.xml')
 run(['uv','run','--frozen','poe','prek-install'],sdk)
 try:
  output=run(['uv','run','--frozen','--group','tool-hooks','prek','run','--files',*[n[len('python/'):]for n in s['files']]],sdk)
  r['normal_scoped_hooks_passed']=True;r['hook_skips']=output.decode().count('Skipped')
 finally:r['post_hook_diff_base64']=base64.b64encode(git('diff','--full-index','--binary')).decode()
 exact();r['state']='confirmed three public Agent.run null regressions with three controls; owning tests and hooks passed'
except BaseException as error:r.update(state='failed_or_partial',error=repr(error));raise
finally:print('OCT25_MM_RESULT='+json.dumps(r),flush=True)
