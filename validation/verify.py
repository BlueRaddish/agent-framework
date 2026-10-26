"""Read the exact shell recipe, run actual consumers and normal repository checks."""
import base64,json,os,re,sys,xml.etree.ElementTree as ET
from pathlib import Path
from _ao_common import run,sha,junit
C=Path.cwd().resolve();V=Path(__file__).resolve().parent;S=json.loads((V/'spec.json').read_text());P=C.parent/'proof';P.mkdir();py=C/'.venv/bin/python';r={'state':'pending','new_source_PR_published':False,'live_model_calls':False}
def git(*args):return run(['git',*args],C)
def exact(fixed=False,head=None):
 assert git('rev-parse','HEAD').decode().strip()==(head or S['base'])
 assert sha((C/S['doc']).read_bytes())==S['after'if fixed else'before']
 assert {p:sha((C/p).read_bytes())for p in S['configs']}==S['configs']
 assert git('diff','--name-only',S['base']).decode().splitlines()==([S['doc']]if fixed else[])
def recipe():
 text=(C/S['doc']).read_text();section=text.split('### Lock the policy against application code\n',1)[1].split('\n### ',1)[0]
 block=re.search(r'```bash\n(.*?)\n```',section,re.S);assert block
 result={}
 for line in block[1].splitlines():
  m=re.fullmatch(r'export ([A-Z_]+)=([A-Z_a-z0-9]+)',line);assert m,line
  assert m[1]not in result;result[m[1]]=m[2]
 assert result['ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS']=='false'and result['ADK_TELEMETRY_IGNORE_RUN_CONFIG']=='1'
 return result
def drive(label,failures):
 exports=recipe();rows=[]
 for schema in ['1','2']:
  for mode in ['NO_CONTENT','EVENT_ONLY','SPAN_ONLY','SPAN_AND_EVENT']:
   env={k:''for k in os.environ if k.startswith(('OTEL_','ADK_TELEMETRY_','GOOGLE_','GEMINI_'))}
   env.update(ADK_TELEMETRY_SCHEMA_VERSION_OPT_IN=schema,OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=mode,OTEL_SEMCONV_STABILITY_OPT_IN='gen_ai_latest_experimental');env.update(exports)
   expected_bad=label=='baseline'and mode!='NO_CONTENT'
   raw=run([str(py),str(V/'consumer.py')],C,extra_env=env,expect=1 if expected_bad else 0)
   found=re.findall(rb'OCT25B_ADK_CONSUMER=(\{[^\r\n]*\})',raw);assert len(found)==1
   d=json.loads(found[0]);assert d['real_runner_completed']and d['spans']>0 and d['live_model_or_network_calls']==0
   if expected_bad:
    assert d['resolved_mode']==mode and (d['content_in_logs']or d['content_in_spans'])
   else:assert d['resolved_mode']=='NO_CONTENT'and not d['content_in_logs']and not d['content_in_spans']
   rows.append({'schema':schema,'inherited_mode':mode,'expected_negative':expected_bad,'proof':d})
 assert sum(x['expected_negative']for x in rows)==failures
 return rows
try:
 exact();assert not git('status','--porcelain','--untracked-files=no').strip()
 run(['uv','venv','--python',os.environ['PYTHON_VERSION'],'.venv'],C);run(['uv','sync','--all-extras'],C)
 lock=sha((C/'uv.lock').read_bytes())
 r['baseline']=drive('baseline',6)
 assert sha((V/'final.patch').read_bytes())==S['patch_sha256'];git('apply','--check',str(V/'final.patch'));git('apply',str(V/'final.patch'));exact(True)
 r['fixed']=drive('fixed',0)
 raw=run([str(py),'-m','pytest','tests/unittests/telemetry/test_telemetry_context.py','tests/unittests/telemetry/test_stable_semconv.py','-q','--junitxml='+str(P/'owning.xml')],C);r['owning']=junit(P/'owning.xml')
 run(['uv','tool','install','pre-commit'],C);run(['pre-commit','install'],C)
 try:
  raw=run(['pre-commit','run','--files',S['doc']],C);r['scoped_hook_skips']=raw.decode().count('Skipped')
 finally:r['post_hook_delta_b64']=base64.b64encode(git('diff','--full-index','--binary')).decode()
 exact(True);git('add','--',S['doc']);assert git('diff','--cached','--name-only').decode().splitlines()==[S['doc']]
 person={'GIT_AUTHOR_NAME':'Jeeho Lee','GIT_AUTHOR_EMAIL':'jeeholife2@gmail.com','GIT_COMMITTER_NAME':'Jeeho Lee','GIT_COMMITTER_EMAIL':'jeeholife2@gmail.com','GIT_AUTHOR_DATE':S['commit_date'],'GIT_COMMITTER_DATE':S['commit_date'],'GIT_TRACE2_EVENT':str(P/'native-trace.jsonl')}
 run(['git','commit','-m','docs(telemetry): disable all content paths in the admin lock recipe\n\nSet the OpenTelemetry capture policy alongside the legacy ADK knob,\nso an inherited capture setting cannot defeat the documented opt-out.\n\nAI-assisted with OpenAI Codex.\n'],C,extra_env=person)
 events=[json.loads(x)for x in(P/'native-trace.jsonl').read_text().splitlines()];starts=[x for x in events if x.get('event')=='child_start'and x.get('hook_name')=='pre-commit'];assert starts
 assert all(any(y.get('event')=='child_exit'and y.get('sid')==x.get('sid')and y.get('child_id')==x.get('child_id')and y.get('code')==0 for y in events)for x in starts)
 head=git('rev-parse','HEAD').decode().strip();assert git('rev-parse','HEAD^').decode().strip()==S['base'];exact(True,head)
 r['native']={'head':head,'tree':git('rev-parse','HEAD^{tree}').decode().strip(),'parent':S['base'],'raw_commit_base64':base64.b64encode(git('cat-file','commit',head)).decode(),'normal_hook_starts':starts}
 run(['uv','tool','install','tox==4.65.3','--with','tox-uv==1.37.0'],C);raw=run(['tox','-e',os.environ['TOX_LANE']],C);r['full_tox_passed']=True
 r['full_tox_summaries']=re.findall(r'=+ ([^\r\n]+ in [^\r\n]+) =+',raw.decode())
 assert sha((C/'uv.lock').read_bytes())==lock and not git('status','--porcelain','--untracked-files=no').strip();exact(True,head)
 r['state']='passed exact documented recipe, actual Runner/exporter consumers, owning suites, normal scoped/native hooks and full tox'
except BaseException as error:r.update(state='failed_or_partial',error=repr(error));raise
finally:print('OCT25B_AO_RESULT='+json.dumps(r),flush=True)
