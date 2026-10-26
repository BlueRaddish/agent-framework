"""Run native repository routes for a two-line documentation correction."""
import argparse,base64,hashlib,json
from pathlib import Path
from _mm_common import run,sha
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--phase',choices=['source','personal'],required=True);a=p.parse_args();v=Path(__file__).resolve().parent;s=json.loads((v/'spec.json').read_text());c=Path(a.source).resolve();sdk=c/'python';proof=c.parent/'proof';proof.mkdir(exist_ok=True);r={'state':'pending','phase':a.phase,'personal_verification_claimed':False}
def git(*args):return run(['git',*args],c)
def exact(fixed,head):
 assert git('rev-parse','HEAD').decode().strip()==head
 assert {n:sha((c/n).read_bytes())for n in s['files']}==s['after' if fixed else 'before']
 assert {n:sha((c/n).read_bytes())for n in s['source_sha256']}==s['source_sha256']
 assert {n:sha((c/n).read_bytes())for n in s['config_sha256']}==s['config_sha256']
 assert sha(git('diff','--full-index','--binary',s['base'],'--',*s['files']))==(s['patch_sha256']if fixed else sha(b''))
 assert set(git('diff','--name-only',s['base']).decode().splitlines())==(set(s['files'])if fixed else set())
try:
 exact(False,s['base']);git('switch','-c','fix/oct25b-mm-skills-model-docs')
 run(['uv','run','--frozen','poe','install'],sdk);exact(False,s['base'])
 command=['uv','run','--python','3.11','--frozen','--no-sync','python',str(v/'consumer.py'),'--source',str(c)]
 if a.phase=='source':run(command+['--baseline'],sdk)
 assert sha((v/'final.patch').read_bytes())==s['patch_sha256'];git('apply','--check',str(v/'final.patch'));git('apply',str(v/'final.patch'));exact(True,s['base'])
 run(command,sdk);r['consumers_passed']=6
 if a.phase=='personal':print('OCT25B_USER_VERIFY='+json.dumps({'scope_id':s['scope'],'base':s['base'],'patch_sha256':s['patch_sha256'],'commands':[command],'exit_codes':[0]}),flush=True)
 else:
  run(['uv','run','--frozen','poe','prek-install'],sdk)
  hooks=run(['uv','run','--frozen','--group','tool-hooks','prek','run','--files',*[n[len('python/'):]for n in s['files']]],sdk);r['normal_scoped_hooks_passed']=True;r['hook_skips']=hooks.decode().count('Skipped');exact(True,s['base'])
  git('add','--',*s['files']);trace=proof/'native-trace.jsonl'
  env={'GIT_AUTHOR_NAME':'Jeeho Lee','GIT_AUTHOR_EMAIL':'jeeholife2@gmail.com','GIT_COMMITTER_NAME':'Jeeho Lee','GIT_COMMITTER_EMAIL':'jeeholife2@gmail.com','GIT_AUTHOR_DATE':s['commit_date'],'GIT_COMMITTER_DATE':s['commit_date'],'GIT_TRACE2_EVENT':str(trace)}
  run(['git','commit','-m',s['title']+'\n\nAI-assisted with OpenAI Codex.'],c,extra_env=env)
  events=[json.loads(x)for x in trace.read_text().splitlines()];starts=[x for x in events if x.get('event')=='child_start'and x.get('hook_name')=='pre-commit'];assert starts
  assert all(any(y.get('event')=='child_exit'and y.get('sid')==x.get('sid')and y.get('child_id')==x.get('child_id')and y.get('code')==0 for y in events)for x in starts)
  head=git('rev-parse','HEAD').decode().strip();assert git('rev-parse','HEAD^').decode().strip()==s['base'];exact(True,head);assert not git('status','--porcelain','--untracked-files=no').strip()
  raw=git('cat-file','commit',head);assert hashlib.sha1(b'commit '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==head
  r['native']={'head':head,'tree':git('rev-parse','HEAD^{tree}').decode().strip(),'parent':s['base'],'raw_commit_base64':base64.b64encode(raw).decode(),'hook_events':events}
 r['state']='passed six offline sample configuration cases'+(' and normal scoped/native commit hooks'if a.phase=='source'else '; actual human initiation recorded separately')
except BaseException as error:r.update(state='failed_or_partial',error=repr(error));raise
finally:print('OCT25B_MS_RESULT='+json.dumps(r),flush=True)
