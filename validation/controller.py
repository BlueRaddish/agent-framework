"""Independent exact-source CI consumer review; no cloud or author-source writes."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

C = Path(__file__).resolve().parent
S = json.loads((C / 'manifest.json').read_text())
P = Path('/tmp/oct23-cmux-proof')
P.mkdir()
R = {'state': 'running', 'spec': S, 'commands': [], 'source_publications': [],
     'cloud_requests': False, 'actual_transport': 'Author local gh/curl/OIDC fixtures; no GitHub artifact/R2 service accessed.'}
W = Path('/tmp/oct23-cmux')
W.mkdir()


def need(x, message):
    if not x:
        raise RuntimeError(message)


def save():
    (P / 'result.json').write_text(json.dumps(R, indent=2))


def run(args, cwd=W, expected=0, timeout=600):
    p = subprocess.run(args, cwd=cwd, env=os.environ.copy(), stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=timeout)
    need(len(p.stdout) < 4 * 1024**2, 'Command output too large')
    text = p.stdout.decode('utf8', 'replace')
    R['commands'].append(dict(command=args, cwd=str(cwd), exit_code=p.returncode, stdout=text))
    save()
    print('OCT23_COMMAND=' + json.dumps(R['commands'][-1]), flush=True)
    need(p.returncode == expected, 'Command exit mismatch: ' + repr(args))
    return text


def exact():
    need(run(['git', 'rev-parse', 'HEAD']).strip() == S['head'], 'Wrong exact head')
    need(not run(['git', 'status', '--porcelain', '--untracked-files=no']).strip(), 'Dirty tracked source')
    for name, sha in S['source_sha256'].items():
        need(hashlib.sha256((W / name).read_bytes()).hexdigest() == sha, 'Source differs: ' + name)


def tap(label, output, tests=None, failures=0):
    count = {}
    for key in ['tests', 'pass', 'fail', 'skipped', 'cancelled']:
        matches = re.findall(r'^# ' + key + r' (\d+)\s*$', output, re.M)
        need(len(matches) == 1, 'Missing/ambiguous TAP count: ' + key)
        count[key] = int(matches[0])
    need(count['tests'] > 0 and (tests is None or count['tests'] == tests), 'Empty/wrong test count')
    need(count['fail'] == failures and count['skipped'] == count['cancelled'] == 0, 'Wrong TAP outcome')
    need(count['pass'] == count['tests'] - failures, 'Unexpected TAP passes')
    R[label] = count
    save()


try:
    need(not any(os.environ.get(k) for k in ['GH_TOKEN', 'GITHUB_TOKEN', 'CLOUDFLARE_API_TOKEN']), 'Unexpected service credentials')
    os.environ.update(WRANGLER_SEND_METRICS='false', CI='true')
    run(['git', 'init', '--initial-branch=oct23-review'])
    run(['git', 'remote', 'add', 'origin', 'https://github.com/manaflow-ai/cmux.git'])
    run(['git', 'fetch', '--depth=2', '--filter=blob:none', 'origin', S['head']])
    run(['git', 'checkout', '--detach', S['head']])
    need(run(['git', 'rev-list', '--parents', '-n', '1', 'HEAD']).strip().split() ==
         [S['head'], *S['head_parents']], 'Wrong real merge parents')
    exact()
    worker = W / 'workers/ci-artifacts'
    run(['node', '--version'])
    run(['npm', '--version'])
    run(['npm', 'ci'], cwd=worker, timeout=900)
    exact()
    target = W / S['test_file']
    fixed = target.read_bytes()
    baseline = subprocess.check_output(['git', 'show', S['baseline'] + ':' + S['test_file']], cwd=W)
    need(hashlib.sha256(baseline).hexdigest() == S['baseline_test_sha256'], 'Wrong original test source')
    try:
        target.write_bytes(baseline)
        output = run(['node', '--test', '--test-reporter=tap', 'test/consumer-workflow.test.mjs'], cwd=worker, expected=1)
        tap('baseline', output, tests=4, failures=4)
        need(output.count("Cannot read properties of undefined (reading 'permissions')") == 4, 'Different baseline failure')
    finally:
        target.write_bytes(fixed)
    exact()
    output = run(['node', '--test', '--test-reporter=tap', 'test/consumer-workflow.test.mjs'], cwd=worker)
    tap('fixed', output, tests=2)
    independent = worker / 'test/oct23-independent-review.test.mjs'
    need(not independent.exists(), 'Independent test file exists')
    independent.write_bytes((C / 'test_consumers.mjs').read_bytes())
    try:
        output = run(['node', '--test', '--test-reporter=tap', 'test/oct23-independent-review.test.mjs'], cwd=worker)
        tap('independent', output, tests=6)
    finally:
        independent.unlink()
    run(['npm', 'run', 'typecheck'], cwd=worker)
    run(['npm', 'run', 'build:test'], cwd=worker)
    tests = [p.relative_to(worker).as_posix() for p in sorted((worker / 'test').glob('*.test.mjs'))]
    need(len(tests) >= 3, 'Missing owner suites')
    output = run(['node', '--test', '--test-reporter=tap', *tests], cwd=worker, timeout=900)
    tap('owning', output)
    need(R['owning']['tests'] >= 39, 'Owner suite unexpectedly small')
    exact()
    R.update(state='passed', normal_native_hook='Not run: read-only review, no source commit.',
             limits='Linux workflow-expression and worker-local fixture scope; no actual GitHub artifact/R2/OIDC service, hosted Mac shell-regressions job, app build or nightly run.')
except BaseException as error:
    R.update(state='failed_or_partial', error=repr(error))
    raise
finally:
    save()
