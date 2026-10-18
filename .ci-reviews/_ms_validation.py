"""Validate the exact existing-PR append; personal mode never commits or publishes."""
import argparse,base64,hashlib,json
from pathlib import Path
from _mm_common import run,junit,sha,git_blob
def main():
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--phase',choices=['source-validation','personal-verification'],required=True);a=p.parse_args()
    packet=Path(__file__).resolve().parent;spec=json.loads((packet/'ms-oct17e-content-docs.json').read_text())
    source=Path(a.source).resolve();sdk=source/'python';proof=source.parent/'proof';proof.mkdir(exist_ok=True)
    combined=packet/spec['patch_name'];append=packet/spec['apply_patch_name']
    assert sha(combined.read_bytes())==spec['patch_sha256'] and sha(append.read_bytes())==spec['append_patch_sha256']
    def exact(fixed,head):
        assert run(['git','rev-parse','HEAD'],source).decode().strip()==head
        expected=spec['final_source'] if fixed else spec['start_source']
        for name,item in expected.items():
            raw=(source/name).read_bytes();assert sha(raw)==item['sha256'] and git_blob(raw)==item['blob']
        assert {name:sha((source/name).read_bytes()) for name in spec['config_sha256']}==spec['config_sha256']
        diff=run(['git','diff','--binary','--full-index','--no-ext-diff','--no-textconv',spec['base'],'--',*spec['files']],source,log_stdout=False)
        assert sha(diff)==(spec['patch_sha256'] if fixed else spec['old_reviewed_patch_sha256'])
        print('OCT17E_MS_SOURCE='+json.dumps({'head':head,'review_base':spec['base'],'native_parent':spec['native_parent'],'combined_patch_sha256':sha(diff),'fixed':fixed,'source_configuration_unchanged':True}),flush=True)
    assert run(['git','status','--porcelain','--untracked-files=no'],source)==b''
    exact(False,spec['start_head'])
    run(['git','switch','-c','fix/oct17e-mm-native-content-docs'],source)
    assert run(['uv','--version'],source).decode().split()[:2]==['uv','0.13.1']
    run(['uv','run','--frozen','poe','install'],sdk)
    lock=sha((sdk/'uv.lock').read_bytes())
    if a.phase=='source-validation':
        command=spec['test_commands'][2]
        run([*command[:-1],'baseline'],sdk)
    run(['git','apply','--check',str(append)],source);run(['git','apply',str(append)],source)
    exact(True,spec['start_head'])
    run(['uv','python','install','3.10','3.11'],sdk)
    for command in spec['test_commands']:run(command,sdk)
    owning=junit(proof/'ms-owning.xml',tests=478)
    assert sha((sdk/'uv.lock').read_bytes())==lock
    exact(True,spec['start_head'])
    if a.phase=='personal-verification':
        print('OCT13_USER_VERIFY='+json.dumps({'scope_id':spec['scope_id'],'base_sha':spec['base'],'patch_sha256':spec['patch_sha256'],'test_commands':spec['test_commands'],'exit_codes':[0]*4}),flush=True)
        return
    run(['uv','run','--frozen','poe','prek-install'],sdk)
    run(['uv','run','--frozen','--group','tool-hooks','prek','run','--files','packages/core/agent_framework/_types.py'],sdk)
    exact(True,spec['start_head'])
    run(['git','add','--',*spec['files']],source)
    trace=proof/'ms-native-trace.jsonl'
    env={'GIT_AUTHOR_NAME':'Jeeho Lee','GIT_AUTHOR_EMAIL':'jeeholife2@gmail.com','GIT_COMMITTER_NAME':'Jeeho Lee','GIT_COMMITTER_EMAIL':'jeeholife2@gmail.com','GIT_AUTHOR_DATE':spec['commit_date'],'GIT_COMMITTER_DATE':spec['commit_date'],'GIT_TRACE2_EVENT':str(trace)}
    run(['git','commit','-m',spec['title']],source,extra_env=env)
    events=[json.loads(x) for x in trace.read_text().splitlines()]
    starts=[x for x in events if x.get('event')=='child_start' and x.get('hook_name')=='pre-commit']
    assert starts and all(any(y.get('event')=='child_exit' and y.get('sid')==x.get('sid') and y.get('child_id')==x.get('child_id') and y.get('code')==0 for y in events) for x in starts)
    assert run(['git','status','--porcelain','--untracked-files=no'],source)==b''
    head=run(['git','rev-parse','HEAD'],source).decode().strip()
    assert run(['git','rev-parse','HEAD^'],source).decode().strip()==spec['native_parent']
    raw=run(['git','cat-file','commit',head],source,log_stdout=False)
    assert hashlib.sha1(b'commit '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==head
    exact(True,head);assert sha((sdk/'uv.lock').read_bytes())==lock
    print('OCT17E_MS_NATIVE='+json.dumps({'scope_id':spec['scope_id'],'head':head,'tree':run(['git','rev-parse','HEAD^{tree}'],source).decode().strip(),'native_parent':spec['native_parent'],'raw_commit_base64':base64.b64encode(raw).decode(),'normal_hook_events':events,'source_configuration_lock_unchanged':True,'owning':owning,'review_base':spec['base'],'combined_patch_sha256':spec['patch_sha256'],'append_patch_sha256':spec['append_patch_sha256']}),flush=True)
if __name__=='__main__':main()
