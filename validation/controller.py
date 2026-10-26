import base64,hashlib,json,os,subprocess,sys
from pathlib import Path
C=Path(__file__).resolve().parent;S=json.loads((C/'manifest.json').read_text());P=Path('/tmp/oct25b-vc-cmux-proof');P.mkdir();W=Path('/tmp/oct25b-vc-cmux');R={'state':'running','spec':S,'commands':[],'mutations':[]}
def save():(P/'result.json').write_text(json.dumps(R,indent=2))
def run(args,expected=0,cwd=None,env=None):
 p=subprocess.run(args,cwd=cwd or W,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=600);assert len(p.stdout)<6*1024**2;e={'args':args,'exit':p.returncode,'stdout':p.stdout.decode('utf8','replace')};R['commands'].append(e);save();print('OCT25B_VC_COMMAND='+json.dumps(e),flush=True);assert p.returncode==expected,e;return p.stdout
try:
 run(['git','clone','--filter=blob:none','--no-checkout','--depth=1','https://github.com/manaflow-ai/cmux.git',str(W)],cwd=C)
 run(['git','fetch','--depth=1','origin',S['base']]);run(['git','checkout','-b',S['branch'],S['base']]);assert run(['git','rev-parse','HEAD']).decode().strip()==S['base']
 assert hashlib.sha256((C/'regression.patch').read_bytes()).hexdigest()==S['patch_sha256'];run(['git','apply',str(C/'regression.patch')]);run(['bash','scripts/install-git-hooks.sh']);run(['git','config','user.name','Jeeho Lee']);run(['git','config','user.email','jeeholife2@gmail.com'])
 testdir=W/'cmux-tui/bindings/python/tests';env=os.environ.copy();env['PYTHONPATH']=str(testdir.parent);cmd=[sys.executable,'-m','unittest','test_resource_api.ResourceApiTests.test_aio_repeated_cancellation_drains_request_before_returning']
 red=run(cmd,1,cwd=testdir,env=env);assert b'request worker was not drained' in red and b'Ran 1 test' in red and b'FAILED (failures=1)' in red;R['baseline']={'tests':1,'failure':'request worker was not drained'}
 run(['git','add','cmux-tui/bindings/python/tests/test_resource_api.py']);run(['git','commit','-m','test(python): reproduce repeated request cancellation drain\n\nAI-assisted with OpenAI Codex.']);R['red_commit']=run(['git','rev-parse','HEAD']).decode().strip()
 target=W/'cmux-tui/bindings/python/cmux/aio.py';old=target.read_text();anchor="                await asyncio.shield(future)\n            except BaseException:\n                # Drain the worker result.";replacement=anchor.replace('await asyncio.shield(future)','await _await_cleanup(future)');assert old.count(anchor)==1;target.write_text(old.replace(anchor,replacement));green=run(cmd,cwd=testdir,env=env);assert b'Ran 1 test' in green and b'OK' in green
 owner=run([sys.executable,'-m','unittest','discover','-s','cmux-tui/bindings/python/tests'],env=env);assert b'OK' in owner and b'Ran ' in owner;R['owners_stdout']=owner.decode()
 run([sys.executable,'scripts/verify-local.py','--affected',S['base']]);run(['git','add','cmux-tui/bindings/python/cmux/aio.py']);run(['git','commit','-m','fix(python): drain request workers after repeated cancellation\n\nReuse cancellation-safe cleanup while waiting for the request.cancel handshake.\nFocused public SDK regression: base fails; repaired head passes.\nAI-assisted with OpenAI Codex.']);R['green_commit']=run(['git','rev-parse','HEAD']).decode().strip();assert not run(['git','status','--porcelain','--untracked-files=no']).strip();run(['git','diff','--check',S['base']]);patch=run(['git','diff','--binary',S['base']]);(P/'final.patch').write_bytes(patch);R['final_patch_base64']=base64.b64encode(patch).decode();R['native_commits']=[]
 for head in [R['red_commit'],R['green_commit']]:
  raw=run(['git','cat-file','commit',head]);R['native_commits'].append({'sha':head,'raw_base64':base64.b64encode(raw).decode()})
 for path in ['cmux-tui/bindings/python/tests/test_resource_api.py','cmux-tui/bindings/python/cmux/aio.py']:
  raw=(W/path).read_bytes();R.setdefault('result_files',{})[path]={'sha256':hashlib.sha256(raw).hexdigest(),'data_base64':base64.b64encode(raw).decode()}
 R['state']='passed'
except BaseException as e:R.update(state='failed_or_partial',error=repr(e));raise
finally:save()
