"""Run real frozen library paths. Failures are expected only with explicit JUnit counts."""
import base64
import json
import locale
import os
import sys
from pathlib import Path
from common import run, junit, sha
c = Path.cwd().resolve()
v = Path(__file__).resolve().parent
kind = sys.argv[1]
s = json.loads((v / 'spec.json').read_text())['adk' if kind == 'adk' else 'oh']
p = c.parent / ('proof-' + kind)
p.mkdir()
os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
record = {'state': 'pending', 'kind': kind, 'head': s['head'], 'live_model_calls': False, 'source_PR_written': False}
py = c / ('.venv/Scripts/python.exe' if sys.platform == 'win32' else '.venv/bin/python')
def git(*args): return run(['git', *args], c)
def exact():
    assert git('rev-parse', 'HEAD').decode().strip() == s['head']
    assert not git('status', '--porcelain', '--untracked-files=no').strip()
    for name, expected in (s['source_sha256'] | s['config_sha256']).items(): assert sha((c/name).read_bytes()) == expected
def test(label, args, failures=0, tests=None):
    raw = run([str(py), '-m', 'pytest', *args, '-q', '--junitxml=' + str(p/(label+'.xml'))], c, expect=1 if failures else 0)
    result = junit(p/(label+'.xml'), failures=failures, tests=tests)
    if failures: assert b'AssertionError' in raw and b'ERROR collecting' not in raw and b'ImportError:' not in raw
    return result
try:
    exact()
    if kind == 'adk':
        run(['uv', 'venv', '--python', '3.13', '.venv'], c)
        run(['uv', 'sync', '--all-extras'], c)
    else: run(['uv', 'sync', '--frozen', '--group', 'dev', '--python', '3.13'], c)
    exact()
    doctor = "import hashlib,sys,locale;from pathlib import Path;import importlib;m=importlib.import_module(sys.argv[1]);p=Path(m.__file__).resolve();assert p==Path(sys.argv[2]).resolve();assert hashlib.sha256(p.read_bytes()).hexdigest()==sys.argv[3];print(sys.version);print(p);print(locale.getencoding());print(sys.flags.utf8_mode)"
    module = 'google.adk.memory._sqlite_memory_service' if kind == 'adk' else 'openhands.sdk.conversation.impl.local_conversation'
    run([str(py), '-c', doctor, module, str(c/s['production'][0]), s['source_sha256'][s['production'][0]]], c)
    if kind == 'adk':
        author = ['tests/unittests/memory/test_sqlite_memory_service.py', 'tests/unittests/tools/test_load_memory_tool.py', '-k', 'test_search_returns_visible_parts_without_mutating_events or test_search_does_not_match_thought_text or test_search_filters_preexisting_thoughts_without_rewriting_storage or test_runner_loads_only_visible_sqlite_memory']
        record['fixed_author'] = test('fixed-author', author, tests=14)
        record['fixed_independent'] = test('fixed-independent', [str(v/'test_adk_consumer.py')], tests=6)
        target = c/s['production'][0]
        fixed = target.read_bytes()
        try:
            target.write_bytes((v/'adk-baseline-0.py').read_bytes())
            record['baseline_author'] = test('baseline-author', author, failures=12, tests=14)
            record['baseline_independent'] = test('baseline-independent', [str(v/'test_adk_consumer.py')], failures=4, tests=6)
        finally: target.write_bytes(fixed)
        exact()
        record['owning'] = test('owning', ['tests/unittests/memory/test_sqlite_memory_service.py', 'tests/unittests/memory/test_in_memory_memory_service.py', 'tests/unittests/tools/test_load_memory_tool.py', 'tests/unittests/tools/test_preload_memory_tool.py'])
    elif kind == 'oh-windows':
        run([str(py), '-c', "import sys,locale;assert sys.platform=='win32';assert sys.flags.utf8_mode==0;assert locale.getencoding().lower()=='cp1252';print('NATIVE_CP1252_CONFIRMED')"], c)
        record['fixed_independent'] = test('fixed-independent', [str(v/'test_oh_consumer.py')], failures=2, tests=16)
        originals = {name:(c/name).read_bytes() for name in s['production']}
        try:
            for n, name in enumerate(s['production']): (c/name).write_bytes((v/('oh-baseline-'+str(n)+'.py')).read_bytes())
            record['baseline_independent'] = test('baseline-independent', [str(v/'test_oh_consumer.py')], failures=8, tests=16)
        finally:
            for name, raw in originals.items(): (c/name).write_bytes(raw)
        exact()
    else:
        author = ['tests/sdk/conversation/local/test_client_tools_persistence.py']
        record['author_suite'] = test('author-suite', author, failures=1, tests=3)
        record['independent_utf8_controls'] = test('independent-utf8-controls', [str(v/'test_oh_consumer.py')], tests=16)
        record['owning'] = test('owning', ['tests/sdk/profiles', 'tests/sdk/llm/test_llm_profile_store.py'])
    if kind != 'oh-windows':
        run(['uv', 'tool', 'install', 'pre-commit'], c) if kind == 'adk' else None
        command = ['pre-commit'] if kind == 'adk' else ['uv', 'run', '--no-sync', 'pre-commit']
        try:
            raw = run(command + ['run', '--files', *s['files']], c)
            record['normal_scoped_hooks_passed'] = True
            record['nonapplicable_hook_skips'] = raw.decode().count('Skipped')
        finally:
            delta = git('diff', '--full-index', '--binary')
            record['post_hook_delta_base64'] = base64.b64encode(delta).decode()
            if delta: print('OCT23_AO_FORMATTER_DELTA ' + record['post_hook_delta_base64'], flush=True)
    exact()
    record['state'] = 'passed bounded review checks with explicitly retained expected failures'
except BaseException as error:
    record.update(state='failed_or_partial', error=repr(error))
    raise
finally: print('OCT23_AO_REVIEW_RESULT ' + json.dumps(record), flush=True)
