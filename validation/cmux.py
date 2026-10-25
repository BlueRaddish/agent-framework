"""Actual workflow-extracted fixture behavior, local compiler stand-ins only."""
import hashlib,json,os,subprocess,sys,unittest,importlib.util
from pathlib import Path
C=Path(__file__).resolve().parent;S=json.loads((C/'manifest.json').read_text())['cmux'];P=Path('/tmp/oct25-vc-cmux-proof');P.mkdir();W=Path('/tmp/oct25-vc-cmux');W.mkdir();R={'state':'running','spec':S,'commands':[],'source_publications':[]}
def save():(P/'result.json').write_text(json.dumps(R,indent=2))
def need(x,m):
    if not x:raise RuntimeError(m)
def run(a,expected=0):
    p=subprocess.run(a,cwd=W,env=os.environ.copy(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=300);need(len(p.stdout)<4*1024**2,'Oversize log');e={'command':a,'exit_code':p.returncode,'stdout':p.stdout.decode('utf8','replace')};R['commands'].append(e);save();print('OCT25_COMMAND='+json.dumps(e),flush=True);need(p.returncode==expected,'Command exit mismatch');return p.stdout
try:
    run(['git','init','--initial-branch=oct25-review']);run(['git','remote','add','origin','https://github.com/manaflow-ai/cmux.git']);run(['git','fetch','--depth=2','--filter=blob:none','origin',S['head']]);run(['git','checkout','--detach',S['head']]);need(run(['git','rev-parse','HEAD^']).decode().strip()==S['baseline'],'Wrong true parent')
    for path,sha in S['source_sha256'].items():need(hashlib.sha256((W/path).read_bytes()).hexdigest()==sha,'Source/config drift')
    run([sys.executable,'-m','venv','/tmp/oct25-vc-cmux-env']);PY='/tmp/oct25-vc-cmux-env/bin/python';run([PY,'-m','pip','install','PyYAML==6.0.3'])
    target=W/S['production'];fixed=target.read_bytes();base=run(['git','show',S['baseline']+':'+S['production']]);need(hashlib.sha256(base).hexdigest()==S['baseline_sha256'],'Wrong baseline test')
    try:
        target.write_bytes(base);red=run([PY,str(target)],1);need(b'REUSED_ARCHIVE: unbound variable' in red,'Baseline failure not claimed fixture');R['baseline_stdout']=red.decode()
    finally:target.write_bytes(fixed)
    green=run([PY,str(target)]);need(b'Ran 5 tests' in green and b'OK' in green,'Empty owning suite');R['fixed']={'tests':5,'failures':0,'skipped':0}
    # Verify the actual producer always supplies the variable, not an assumed contract.
    proof=run([PY,'-c',"import pathlib,yaml,json; p=pathlib.Path('.github/workflows/cmux-next.yml'); w=yaml.safe_load(p.read_text()); s=next(s for s in w['jobs']['cmux-scheme-compile']['steps'] if s.get('name')=='Compile the cmux NEXT DEV Release app'); assert 'REUSED_ARCHIVE' in s['env']; assert 'REUSED_ARCHIVE' in s['run']; print(json.dumps({'step':s['name'],'reused_archive_env':s['env']['REUSED_ARCHIVE'],'nounset_consumer':'REUSED_ARCHIVE' in s['run']}))"]);R['producer_contract']=json.loads(proof)
    need(not run(['git','status','--porcelain','--untracked-files=no']).strip(),'Source dirty');R['state']='passed'
except BaseException as e:R.update(state='failed_or_partial',error=repr(e));raise
finally:save()
