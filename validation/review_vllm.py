"""Exact quote scanner regression via a real CPU/empty-target installation."""
import hashlib,json,os,subprocess
from pathlib import Path
import xml.etree.ElementTree as ET
from cpu import install_uv,setup_vllm
C=Path(__file__).resolve().parent;S=json.loads((C/'manifest.json').read_text())['vllm'];P=Path('/tmp/oct25-vc-vllm-proof');P.mkdir();W=Path('/tmp/oct25-vc-vllm');W.mkdir()
R={'state':'running','spec':S,'commands':[],'source_publications':[],'model_inference':False}
def save():(P/'result.json').write_text(json.dumps(R,indent=2))
def need(x,m):
    if not x:raise RuntimeError(m)
def run(a,expected=0,timeout=600):
    p=subprocess.run(a,cwd=W,env=os.environ.copy(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout);need(len(p.stdout)<4*1024**2,'Oversize command output');e={'command':a,'exit_code':p.returncode,'stdout':p.stdout.decode('utf8','replace')};R['commands'].append(e);save();print('OCT25_COMMAND='+json.dumps(e),flush=True);need(p.returncode==expected,'Command exit mismatch');return p.stdout
def exact():
    need(run(['git','rev-parse','HEAD']).decode().strip()==S['head'],'Wrong source');need(not run(['git','status','--porcelain','--untracked-files=no']).strip(),'Dirty source')
    for path,sha in S['source_sha256'].items():need(hashlib.sha256((W/path).read_bytes()).hexdigest()==sha,'Source/config drift:'+path)
def counts(name,tests,failures=0):
    cs=list(ET.parse(P/(name+'.xml')).iter('testcase'));d=dict(tests=len(cs),failures=sum(c.find('failure')is not None for c in cs),errors=sum(c.find('error')is not None for c in cs),skipped=sum(c.find('skipped')is not None for c in cs));need(d==dict(tests=tests,failures=failures,errors=0,skipped=0),'Wrong JUnit result:'+repr(d));R[name]=d;R[name+'_failures']=[{'name':c.attrib['name'],'failure':c.find('failure').text}for c in cs if c.find('failure')is not None];save()
def pytest(name,paths,expected=0):return run([*PREFIX,'.venv/bin/python','-m','pytest','-p','cpu_unit_marker',*paths,'-q','--junitxml='+str(P/(name+'.xml'))],expected)
try:
    need(not any(os.environ.get(x)for x in ['SKIP','PRE_COMMIT_ALLOW_NO_CONFIG','GH_TOKEN','GITHUB_TOKEN']),'Unexpected bypass/credential environment')
    os.environ.update(PYTHONPATH=str(C),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',VLLM_NO_USAGE_STATS='1',DO_NOT_TRACK='1',CUDA_VISIBLE_DEVICES='')
    run(['git','init','--initial-branch=oct25-review']);run(['git','remote','add','origin','https://github.com/vllm-project/vllm.git']);run(['git','fetch','--depth=2','--filter=blob:none','origin',S['head']]);run(['git','checkout','--detach',S['head']]);need(run(['git','rev-list','--parents','-n','1','HEAD']).decode().strip().split()==[S['head'],*S['parents']],'Wrong source parents');exact()
    install_uv();PREFIX=setup_vllm(W);run(['uv','pip','install','pytest==9.1.0','pytest-asyncio==1.4.0','tblib==3.1.0','pandas','matplotlib','seaborn','--torch-backend','cpu']);exact()
    target=W/S['production'];fixed=target.read_bytes();base=run(['git','show',S['baseline']+':'+S['production']]);need(hashlib.sha256(base).hexdigest()==S['baseline_sha256'],'Wrong upstream source')
    try:
        target.write_bytes(base);pytest('parent_compatibility',[str(C/'test_consumers.py')]);counts('parent_compatibility',10)
    finally:target.write_bytes(fixed)
    exact();pytest('head_regression',[str(C/'test_consumers.py')],1);counts('head_regression',10,7)
    need(all('Unterminated quoted value' in c['failure']for c in R['head_regression_failures']),'Unexpected regression cause')
    owner=pytest('owning',[S['test_module']]);cs=list(ET.parse(P/'owning.xml').iter('testcase'));counts('owning',len(cs));need(len(cs)>=42,'Owning coverage shrank')
    # A diagnostic only: consult the existing parsed target before treating a
    # later quote as outer quoting. No source branch/commit is created.
    source=fixed.decode();old='                tuple(PLOT_FILTERS)\n            ):\n';new='                tuple(PLOT_FILTERS)\n            ) and PlotFilterBase.parse_str(s[start:index]).target == "":\n';need(source.count(old)==1,'Diagnostic patch anchor drift')
    try:
        target.write_text(source.replace(old,new));pytest('diagnostic_repair',[str(C/'test_consumers.py'),S['test_module']]);counts('diagnostic_repair',10+len(cs))
    finally:target.write_bytes(fixed)
    exact();R['state']='passed'
except BaseException as e:R.update(state='failed_or_partial',error=repr(e));raise
finally:save()
