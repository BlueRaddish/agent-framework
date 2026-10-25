"""Execute the real frozen consuming paths and preserve explicit failed controls."""
import base64,json,os,sys
from pathlib import Path
from common import run,junit,sha
C=Path.cwd().resolve();V=Path(__file__).resolve().parent;kind=sys.argv[1]
S=json.loads((V/'spec.json').read_text());s=S['adk'if kind=='adk'else'oh'];P=C.parent/('proof-'+kind);P.mkdir()
os.environ['LITELLM_LOCAL_MODEL_COST_MAP']='True'
record={'state':'pending','kind':kind,'head':s['head'],'source_PR_pushed':False,'live_model_calls':False}
py=C/('.venv/Scripts/python.exe'if sys.platform=='win32'else'.venv/bin/python')
def git(*args):return run(['git',*args],C)
def exact(final=False):
    assert git('rev-parse','HEAD').decode().strip()==s['head']
    for p,h in (s['source_sha256']|s['config_sha256']).items():
        want=s['final_test_sha256']if final and p==s['files'][0]and kind=='adk'else h
        assert sha((C/p).read_bytes())==want,p
def tests(label,args,failures=0,count=None):
    raw=run([str(py),'-m','pytest',*args,'-q','--junitxml='+str(P/(label+'.xml'))],C,expect=1 if failures else 0)
    result=junit(P/(label+'.xml'),failures=failures,tests=count)
    if failures:assert b'ERROR collecting'not in raw and b'ImportError:'not in raw
    return result
try:
    exact();assert not git('status','--porcelain','--untracked-files=no').strip()
    if kind=='adk':
        run(['uv','venv','--python',os.environ['PYTHON_VERSION'],'.venv'],C);run(['uv','sync','--all-extras'],C)
        lock=sha((C/'uv.lock').read_bytes())
        target=C/s['files'][0];target.write_bytes((V/'adk-final-test.py').read_bytes());exact(True)
        focused=[s['files'][0]+'::TestLowercaseSchemaTypes::test_boolean_array_tail_schema_is_preserved',s['files'][0]+'::TestLowercaseSchemaTypes::test_array_tail_schema_keeps_nested_data_values']
        record['focused']=tests('focused',focused,count=6)
        prod=C/s['production'][0];original=prod.read_bytes()
        try:
            prod.write_bytes((V/'adk-baseline-0.py').read_bytes())
            record['negative_original']=tests('negative-original',focused,failures=2,count=6)
        finally:prod.write_bytes(original)
        exact(True)
        record['owning']=tests('owning',['tests/unittests/utils/test_schema_utils.py','tests/unittests/models/test_anthropic_llm.py','tests/unittests/models/test_litellm.py'])
        run(['uv','tool','install','pre-commit'],C);run(['pre-commit','install'],C)
        try:
            hooks=run(['pre-commit','run','--files',*s['files']],C)
            record['scoped_hook_skips']=hooks.decode().count('Skipped')
        finally:
            delta=git('diff','--full-index','--binary');record['post_hook_patch_b64']=base64.b64encode(delta).decode()
        exact(True)
        git('add','--',*s['files'])
        assert git('diff','--cached','--name-only').decode().splitlines()==s['files']
        person=S['person'];env={key:person[val]for key,val in [('GIT_AUTHOR_NAME','name'),('GIT_AUTHOR_EMAIL','email'),('GIT_AUTHOR_DATE','date'),('GIT_COMMITTER_NAME','name'),('GIT_COMMITTER_EMAIL','email'),('GIT_COMMITTER_DATE','date')]}
        trace=P/'commit-trace.jsonl';env['GIT_TRACE2_EVENT']=str(trace)
        run(['git','commit','-m','test(schema): cover array-tail booleans and nested data values\n\nAddress the focused helper regression suggestion on #7531.\nProduction conversion behavior remains unchanged.\n\nAI-assisted with OpenAI Codex.\n'],C,extra_env=env)
        events=[json.loads(x)for x in trace.read_text().splitlines()]
        starts=[x for x in events if x.get('event')=='child_start'and(x.get('hook_name')=='pre-commit'or any('hooks/pre-commit'in str(a)for a in x.get('argv',[])))]
        assert starts and all(any(x.get('event')=='child_exit'and x.get('sid')==a.get('sid')and x.get('child_id')==a.get('child_id')and x.get('code')==0 for x in events)for a in starts)
        head=git('rev-parse','HEAD').decode().strip();raw=git('cat-file','commit',head)
        assert git('show','--format=%P','--no-patch',head).decode().strip()==s['head']
        assert git('diff','--name-only',s['head'],head).decode().splitlines()==s['files']
        assert not git('status','--porcelain','--untracked-files=no').strip()
        record['native']={'head':head,'tree':git('rev-parse','HEAD^{tree}').decode().strip(),'parents':[s['head']],'commit_raw_base64':base64.b64encode(raw).decode(),'normal_hook_starts':starts}
        run(['uv','tool','install','tox==4.65.3','--with','tox-uv==1.37.0'],C)
        run(['tox','-e',os.environ['TOX_LANE']],C)
        record['full_tox_passed']=True
        assert sha((C/'uv.lock').read_bytes())==lock and sha(target.read_bytes())==s['final_test_sha256']
        assert not git('status','--porcelain','--untracked-files=no').strip()
    else:
        run(['uv','sync','--frozen','--group','dev','--python','3.13'],C);exact()
        doctor="import sys,locale;from pathlib import Path;import openhands.sdk.conversation.impl.local_conversation as m;assert Path(m.__file__).resolve()==Path(sys.argv[1]).resolve();print(sys.version);print(locale.getencoding());print(sys.flags.utf8_mode)"
        run([str(py),'-c',doctor,str(C/s['production'][0])],C)
        if kind=='oh-windows':
            run([str(py),'-c',"import sys,locale;assert sys.platform=='win32'and sys.flags.utf8_mode==0 and locale.getencoding().lower()=='cp1252';print('NATIVE_CP1252_CONFIRMED')"],C)
            record['fixed_independent']=tests('fixed-independent',[str(V/'test_oh_consumer.py')],count=16)
            originals={p:(C/p).read_bytes()for p in s['production']}
            try:
                for i,p in enumerate(s['production']):(C/p).write_bytes((V/('oh-baseline-'+str(i)+'.py')).read_bytes())
                record['baseline_independent']=tests('baseline-independent',[str(V/'test_oh_consumer.py')],failures=8,count=16)
            finally:
                for p,b in originals.items():(C/p).write_bytes(b)
        else:
            author=['tests/sdk/conversation/local/test_client_tools_persistence.py::test_recover_persisted_client_tools_decodes_base_state_as_utf8','tests/sdk/llm/test_llm_json_storage.py::test_llm_load_from_json_decodes_utf8_regardless_of_locale']
            record['fixed_author']=tests('fixed-author',author,count=2)
            originals={p:(C/p).read_bytes()for p in s['production']}
            try:
                for i,p in enumerate(s['production']):(C/p).write_bytes((V/('oh-baseline-'+str(i)+'.py')).read_bytes())
                record['baseline_author']=tests('baseline-author',author,failures=2,count=2)
            finally:
                for p,b in originals.items():(C/p).write_bytes(b)
            record['fixed_independent']=tests('fixed-independent',[str(V/'test_oh_consumer.py')],count=16)
            record['owning']=tests('owning',['tests/sdk/profiles','tests/sdk/llm/test_llm_profile_store.py','tests/sdk/llm/test_llm_json_storage.py','tests/sdk/conversation/local/test_client_tools_persistence.py'])
            try:
                raw=run(['uv','run','--no-sync','pre-commit','run','--files',*s['files']],C)
                record['normal_scoped_hooks_passed']=True;record['nonapplicable_hook_skips']=raw.decode().count('Skipped')
            finally:record['post_hook_delta_b64']=base64.b64encode(git('diff','--full-index','--binary')).decode()
        exact();assert not git('status','--porcelain','--untracked-files=no').strip()
    record['state']='passed exact bounded consumers and explicitly retained negative controls'
except BaseException as error:
    record.update(state='failed_or_partial',error=repr(error));raise
finally:print('OCT25_AO_RESULT '+json.dumps(record),flush=True)
