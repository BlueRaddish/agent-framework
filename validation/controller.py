"""Exact outside-author CPU parser review, using the established installation route."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from cpu import install_uv, setup_vllm

CONTROL = Path(__file__).resolve().parent
SPEC = json.loads((CONTROL / 'manifest.json').read_text())
PROOF = Path('/tmp/oct23-vc-proof')
PROOF.mkdir()
CWD = Path('/tmp/oct23-vc-vllm')
CWD.mkdir()
RESULT = dict(state='running', spec=SPEC, commands=[], source_publications=[], model_inference=False)


def need(value, message):
    if not value:
        raise RuntimeError(message)


def save():
    (PROOF / 'result.json').write_text(json.dumps(RESULT, indent=2))


def run(args, *, expected=0, timeout=600):
    p = subprocess.run(args, cwd=CWD, env=os.environ.copy(), stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=timeout)
    need(len(p.stdout) < 4 * 1024**2, 'Command output too large')
    entry = dict(command=args, exit_code=p.returncode, stdout=p.stdout.decode('utf8', 'replace'))
    RESULT['commands'].append(entry)
    save()
    print('OCT23_COMMAND=' + json.dumps(entry), flush=True)
    need(p.returncode == expected, 'Command exit mismatch: ' + repr(args))
    return p.stdout


def exact():
    need(run(['git', 'rev-parse', 'HEAD']).decode().strip() == SPEC['head'], 'Wrong head')
    need(not run(['git', 'status', '--porcelain', '--untracked-files=no']).strip(), 'Dirty tracked source')
    for name, sha in SPEC['source_sha256'].items():
        need(hashlib.sha256((CWD / name).read_bytes()).hexdigest() == sha, 'Source differs: ' + name)


def junit(name, expected_tests=None, failures=0, skips=0):
    cases = list(ET.parse(PROOF / (name + '.xml')).iter('testcase'))
    counts = dict(tests=len(cases), failures=sum(x.find('failure') is not None for x in cases),
                  errors=sum(x.find('error') is not None for x in cases),
                  skipped=sum(x.find('skipped') is not None for x in cases))
    need(counts['tests'] > 0 and (expected_tests is None or counts['tests'] == expected_tests), 'Empty/wrong test count')
    need(counts['failures'] == failures and counts['errors'] == 0 and counts['skipped'] == skips, 'Wrong JUnit outcome')
    RESULT[name] = counts
    RESULT[name + '_failures'] = [{'name': c.attrib['name'], 'failure': c.find('failure').text}
                                for c in cases if c.find('failure') is not None]
    save()


def pytest(name, paths, expected=0):
    return run([*PREFIX, '.venv/bin/python', '-m', 'pytest', '-p', 'cpu_unit_marker', *paths,
                '-q', '--junitxml=' + str(PROOF / (name + '.xml'))], expected=expected)


try:
    need(not any(os.environ.get(x) for x in ('SKIP', 'PRE_COMMIT_ALLOW_NO_CONFIG', 'GH_TOKEN', 'GITHUB_TOKEN')), 'Unexpected bypass/credential environment')
    os.environ.update(PYTHONPATH=str(CONTROL), HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                      VLLM_NO_USAGE_STATS='1', DO_NOT_TRACK='1', CUDA_VISIBLE_DEVICES='')
    run(['git', 'init', '--initial-branch=oct23-review'])
    run(['git', 'remote', 'add', 'origin', 'https://github.com/vllm-project/vllm.git'])
    run(['git', 'fetch', '--depth=2', '--filter=blob:none', 'origin', SPEC['head']])
    run(['git', 'checkout', '--detach', SPEC['head']])
    need(run(['git', 'rev-list', '--parents', '-n', '1', 'HEAD']).decode().strip().split() ==
         [SPEC['head'], *SPEC['head_parents']], 'Wrong real merge parents')
    need(run(['git', 'rev-parse', 'HEAD^2']).decode().strip() == SPEC['baseline'], 'Wrong upstream merge parent')
    exact()
    RESULT['callers'] = run(['git', 'grep', '-n', 'FlexibleArgumentParser', '--', 'vllm/entrypoints/cli', 'vllm/benchmarks/serve.py']).decode()
    install_uv()
    PREFIX = setup_vllm(CWD)
    run(['uv', 'pip', 'install', 'pytest==9.1.0', 'pytest-asyncio==1.4.0', 'tblib==3.1.0', '--torch-backend', 'cpu'])
    exact()
    target = CWD / SPEC['production']
    fixed = target.read_bytes()
    baseline = run(['git', 'show', SPEC['baseline'] + ':' + SPEC['production']])
    need(hashlib.sha256(baseline).hexdigest() == SPEC['baseline_sha256'], 'Wrong parent source')
    focused = [SPEC['test_module'] + '::test_negative_decimal_is_value_not_dict_arg',
               str(CONTROL / 'test_consumers.py')]
    try:
        target.write_bytes(baseline)
        pytest('baseline', focused, expected=1)
        junit('baseline', 18, failures=14)
        failures = RESULT['baseline_failures']
        need(all('test_negative_decimal' in x['name'] for x in failures), 'Control failure')
        need(all(('IndexError' in x['failure'] or 'SystemExit' in x['failure']) and 'argparse_utils.py' in x['failure'] for x in failures), 'Non-regression baseline failure')
    finally:
        target.write_bytes(fixed)
    exact()
    pytest('fixed', focused)
    junit('fixed', 18)
    owner = pytest('owning', [SPEC['test_module'], '-k', 'not test_convert_ids_list_to_tokens'])
    need('1 deselected' in owner.decode(), 'Network-test deselection count differs')
    junit('owning')
    RESULT['network_tests_deselected'] = 1
    try:
        hooks = run([*PREFIX, '.venv/bin/python', '-m', 'pre_commit', 'run', '--files', *SPEC['files']], timeout=1200)
    finally:
        RESULT['post_hook_tracked_diff'] = run(['git', 'diff', '--binary', '--full-index', '--no-ext-diff', '--no-textconv']).decode()
        save()
    RESULT['hook_skips'] = hooks.decode().count('Skipped')
    RESULT['normal_scoped_hooks_passed'] = True
    exact()
    RESULT['state'] = 'passed'
except BaseException as error:
    RESULT.update(state='failed_or_partial', error=repr(error))
    raise
finally:
    RESULT['cpu_setup_receipt'] = str(Path('/tmp/oct23-vc-setup-proof/cpu-commands.json'))
    save()
