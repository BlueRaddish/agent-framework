"""Recheck two existing PRs on real merged source, with no source publication."""
from datetime import datetime, timezone
from pathlib import Path
import base64, hashlib, json, os, re, subprocess, sys
import xml.etree.ElementTree as ET

C = Path(__file__).resolve().parent
S = json.loads((C / 'manifest.json').read_text())
K = sys.argv[1]
T = S['targets'][K]
P = Path('/tmp/oct22-' + K + '-proof')
P.mkdir()
R = {'target': T, 'commands': [], 'source_publications': [], 'started_at': datetime.now(timezone.utc).isoformat()}
def save(): (P / 'result.json').write_text(json.dumps(R, indent=2))
def need(x, m):
    if not x: raise RuntimeError(m)
def run(args, cwd, codes=(0,), timeout=600, env=None):
    p = subprocess.run(args, cwd=cwd, env=env or os.environ.copy(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    need(len(p.stdout) < 4 * 1024**2, 'bounded output exceeded')
    s = p.stdout.decode('utf8', 'replace')
    R['commands'].append({'command': args, 'exit_code': p.returncode, 'stdout': s})
    save(); print('OCT22_COMMAND=' + json.dumps(R['commands'][-1]), flush=True)
    need(p.returncode in codes, 'command failed: ' + repr(args))
    return s
def main():
    need(K in ('cmux', 'vllm'), 'unknown target')
    cwd = Path('/tmp/oct22-' + K)
    cwd.mkdir()
    run(['git', 'init', '--initial-branch=oct22-check'], cwd)
    run(['git', 'remote', 'add', 'origin', 'https://github.com/' + T['repo'] + '.git'], cwd)
    run(['git', 'fetch', '--filter=blob:none', '--depth=' + str(T['depth']), 'origin', T['main'], T['head']], cwd, timeout=600)
    run(['git', 'checkout', '-b', 'oct22-integration', T['head']], cwd)
    need(run(['git', 'merge-base', T['head'], T['main']], cwd).strip() == T['base'], 'ancestry differs')
    run(['git', 'config', 'user.name', S['person']['name']], cwd)
    run(['git', 'config', 'user.email', S['person']['email']], cwd)
    if K == 'cmux':
        from cpu import install_uv
        install_uv()
        run(['uv', 'venv', '--python', '3.12', '/tmp/oct22-cmux-python'], cwd)
        run(['uv', 'pip', 'install', '--python', '/tmp/oct22-cmux-python/bin/python', 'PyYAML', 'pip', 'setuptools>=77', 'wheel'], cwd)
        os.environ['PATH'] = '/tmp/oct22-cmux-python/bin:' + os.environ['PATH']
        run(['bash', 'scripts/install-git-hooks.sh'], cwd)
        # The project's supported resolver is the sole main-integration path.
        trace = str(P / 'merge-trace.jsonl')
        env = {**os.environ, 'GIT_TRACE2_EVENT': trace}
        run(['bash', 'scripts/merge-main.sh', '--tip', '--no-guards'], cwd, env=env)
        need(run(['git', 'show', '-s', '--format=%P', 'HEAD'], cwd).strip() == T['head'] + ' ' + T['main'], 'merge parents differ or main moved')
        events = [json.loads(x) for x in Path(trace).read_text().splitlines()]
        # Upstream's resolver intentionally creates its initial merge with
        # --no-verify. Amend only that unpublished merge through the real
        # current tracked hook; no public history is rewritten.
        R['resolver_trace'] = events
        run(['bash', 'scripts/install-git-hooks.sh'], cwd)
        trace = str(P / 'normal-hook-trace.jsonl')
        run(['git', 'commit', '--amend', '--no-edit'], cwd, env={**os.environ, 'GIT_TRACE2_EVENT': trace})
        events = [json.loads(x) for x in Path(trace).read_text().splitlines()]
        starts = [x for x in events if x.get('event') == 'child_start' and x.get('child_class') == 'hook' and x.get('hook_name') == 'pre-commit']
        need(len(starts) == 1, 'normal current pre-commit hook not executed')
        ends = [x for x in events if x.get('event') == 'child_exit' and x.get('sid') == starts[0]['sid'] and x.get('child_id') == starts[0]['child_id']]
        need(len(ends) == 1 and ends[0]['code'] == 0, 'normal current hook failed')
        R['hook_trace'] = events
        env = {**os.environ, 'PYTHONPATH': str(cwd / 'cmux-tui/bindings/python'), 'PYTHONDONTWRITEBYTECODE': '1'}
        text = run(['python3', '-m', 'unittest', 'discover', '-s', 'cmux-tui/bindings/python/tests', '-v'], cwd, env=env, timeout=900)
        m = re.search(r'Ran (\d+) tests? in', text)
        need(m and int(m[1]) >= 118 and re.search(r'^OK$', text, re.M), 'SDK suite incomplete or skipped')
        R['SDK_tests'] = int(m[1])
        static = run(['python3', 'scripts/verify-local.py', '--all'], cwd, env=env, timeout=900)
        need('PASSED: 16/16 selected checks ran.' in static, 'full static not complete')
        R['full_static'] = '16/16 passed; internal normalizer skip retained in raw output'
    else:
        # Resolve only the known plot parser conflict; retain main's new whitespace semantics.
        run(['git', 'merge', '--no-commit', '--no-ff', T['main']], cwd, codes=(1,))
        conflicts = set(run(['git', 'diff', '--name-only', '--diff-filter=U'], cwd).splitlines())
        need('vllm/benchmarks/sweep/plot.py' in conflicts and conflicts <= {'vllm/benchmarks/sweep/plot.py', 'tests/benchmarks/test_plot_filters.py'}, 'unexpected conflict scope')
        path = 'vllm/benchmarks/sweep/plot.py'
        baseline = subprocess.check_output(['git', 'show', T['main'] + ':' + path], cwd=cwd)
        needle = '''        for op_key in PLOT_FILTERS:
            if op_key in s:
                key, _, value = s.partition(op_key)
                return PLOT_FILTERS[op_key](
                    key.strip(),
                    value.removeprefix(op_key).strip().strip("'").strip('"'),
                )
        else:
            raise ValueError(
                f"Invalid operator for plot filter '{s}'. "
                f"Valid operators are: {sorted(PLOT_FILTERS)}",
            )
'''
        replacement = '''        parts = re.split(r"(==|!=|<=|>=|<|>)", s, maxsplit=1)
        if len(parts) == 3:
            key, op_key, value = parts
            return PLOT_FILTERS[op_key](
                key.strip(),
                value.strip().strip("'").strip('"'),
            )

        raise ValueError(
            f"Invalid operator for plot filter '{s}'. "
            f"Valid operators are: {sorted(PLOT_FILTERS)}",
        )
'''
        raw = baseline.decode()
        need(raw.count(needle) == 1 and 'import regex as re' not in raw, 'current parser changed')
        fixed = raw.replace('from typing_extensions import override', 'import regex as re\nfrom typing_extensions import override').replace(needle, replacement)
        (cwd / path).write_text(fixed)
        run(['git', 'add', '--', path], cwd)
        test_path = 'tests/benchmarks/test_plot_filters.py'
        main_tests = subprocess.check_output(['git', 'show', T['main'] + ':' + test_path], cwd=cwd).decode()
        own_tests = subprocess.check_output(['git', 'show', T['head'] + ':' + test_path], cwd=cwd).decode()
        fragment = '''    @pytest.mark.parametrize(
        "filter_str,expected",
        [
            ("label==build==one", ["build==one"]),
            ("label!=build==one", ["==preview", "other"]),
            ("label====preview", ["==preview"]),
        ],
    )
    def test_string_target_preserves_operator_characters(self, filter_str, expected):
        df = pd.DataFrame({"label": ["build==one", "==preview", "other"]})
        filtered = PlotFilters.parse_str(filter_str).apply(df)
        assert filtered["label"].tolist() == expected

'''
        anchor = '    def test_parse_multiple_filters(self):\n'
        need(own_tests.count(fragment) == 1 and fragment not in main_tests and main_tests.count(anchor) == 1, 'existing regression or main test contract changed')
        merged_tests = main_tests.replace(anchor, fragment + anchor)
        (cwd / test_path).write_text(merged_tests)
        need((cwd / test_path).read_text().replace(fragment, '', 1) == main_tests, 'main test content changed')
        run(['git', 'add', '--', test_path], cwd)
        docs = cwd / 'docs/benchmarking/sweeps.md'
        anchor = 'Control the variables to plot via `--var-x` and `--var-y`, optionally applying `--filter-by` and `--bin-by` to the values. The plot is organized according to `--fig-by`, `--row-by`, `--col-by`, and `--curve-by`.\n'
        addition = '\nString filters split at the first comparison operator (`==`, `!=`, `<=`, `>=`, `<`, or `>`). For example, `--filter-by \'label!=build==one\'` excludes the label `build==one`; later operator characters remain part of the string value.\n'
        text = docs.read_text()
        need(text.count(anchor) == 1, 'documentation anchor changed')
        docs.write_text(text.replace(anchor, anchor + addition))
        run(['git', 'add', '--', 'docs/benchmarking/sweeps.md'], cwd)
        from cpu import install_uv, setup_vllm
        install_uv(); prefix = setup_vllm(cwd)
        run(['uv', 'pip', 'install', 'pandas', 'pytest-asyncio', 'tblib'], cwd)
        run([*prefix, '.venv/bin/python', '-c', "import pathlib,torch; import vllm.benchmarks.sweep.plot as m; assert pathlib.Path(m.__file__).resolve()==pathlib.Path('vllm/benchmarks/sweep/plot.py').resolve(); assert torch.version.cuda is None; print(m.__file__,torch.__version__)"], cwd)
        cmd = [*prefix, '.venv/bin/python', '-m', 'pytest', 'tests/benchmarks/test_plot_filters.py', '--confcutdir=tests/benchmarks', '-q']
        (cwd / path).write_bytes(baseline)
        red = run([*cmd, '--junitxml=' + str(P / 'baseline.xml')], cwd, codes=(1,))
        need('test_string_target_preserves_operator_characters' in red and 'KeyError' in red and 'AssertionError' in red, 'baseline symptom differs')
        need(re.search(r'2 failed, \d+ passed', red) and ' ERROR ' not in red, 'baseline failures are not clean')
        (cwd / path).write_text(fixed)
        green = run([*cmd, '--junitxml=' + str(P / 'fixed.xml')], cwd)
        need(re.search(r'\d+ passed', green) and 'skipped' not in green, 'fixed suite incomplete')
        def cases(name):
            values = {}
            for case in ET.parse(P / name).getroot().iter('testcase'):
                key = (case.get('classname'), case.get('name'))
                need(key not in values and not case.findall('error') and not case.findall('skipped'), 'duplicate, error, or skipped testcase')
                values[key] = len(case.findall('failure'))
            need(values, 'no testcases')
            return values
        red_cases, green_cases = cases('baseline.xml'), cases('fixed.xml')
        need(set(red_cases) == set(green_cases) and sum(red_cases.values()) == 2 and not any(green_cases.values()), 'collection or outcome changed')
        failed = [key[1] for key, count in red_cases.items() if count]
        need(len(failed) == 2 and all('test_string_target_preserves_operator_characters' in n for n in failed) and any('label!=build==one' in n for n in failed) and any('label====preview' in n for n in failed), 'unexpected regression case failed')
        R['junit'] = {'collected': len(red_cases), 'baseline_failed': failed, 'fixed_passed': len(green_cases), 'errors': 0, 'skips': 0, 'same_collected_ids': True}
        tested = {p: hashlib.sha256((cwd / p).read_bytes()).hexdigest() for p in T['files']}
        run(['git', 'add', '--', path], cwd)
        run([*prefix, 'pre-commit', 'run', '--files', *T['files']], cwd, timeout=900)
        need({p: hashlib.sha256((cwd / p).read_bytes()).hexdigest() for p in T['files']} == tested, 'hooks changed tested source/test; inspect instead of accepting')
        need(not run(['git', 'diff', '--name-only'], cwd).strip(), 'tracked unstaged changes after hooks')
        R['baseline_summary'] = re.findall(r'\d+ failed, \d+ passed[^\n]*', red)
        R['fixed_summary'] = re.findall(r'\d+ passed[^\n]*', green)
        R['source_commit_created'] = False
        R['personal_review_and_DCO_pending'] = True
    run(['git', 'diff', '--check'], cwd)
    run(['git', 'diff', '--cached', '--check'], cwd)
    need(not run(['git', 'diff', '--name-only'], cwd).strip(), 'tested working tree differs from staged source')
    tree = run(['git', 'write-tree'], cwd).strip()
    diff = run(['git', 'diff', '--cached', '--binary', T['main']], cwd)
    # Preserve the existing fix, adding only documentation required by current policy.
    expected = sorted(T['files'])
    names = run(['git', 'diff', '--cached', '--name-only', T['main']], cwd).splitlines()
    need(names == expected, 'combined PR scope changed')
    R.update(tree=tree, patch=diff, patch_sha256=hashlib.sha256(diff.encode()).hexdigest(),
             files={p: base64.b64encode((cwd / p).read_bytes()).decode() for p in expected})
    if K == 'cmux':
        head = run(['git', 'rev-parse', 'HEAD'], cwd).strip()
        raw = subprocess.check_output(['git', 'cat-file', 'commit', head], cwd=cwd)
        R.update(head=head, raw_commit_b64=base64.b64encode(raw).decode())
    R['state'] = 'passed exact integration and consuming checks'
    R['completed_at'] = datetime.now(timezone.utc).isoformat()
    save(); print('OCT22_RESULT=' + json.dumps(R), flush=True)
if __name__ == '__main__':
    try: main()
    except BaseException as e:
        cwd = Path('/tmp/oct22-' + K)
        if (cwd / '.git').exists():
            # Preserve actual post-hook changes even when hooks return failure.
            R['failure_diffs'] = {}
            for label, args in [('staged', ['git', 'diff', '--cached', '--binary']), ('unstaged', ['git', 'diff', '--binary'])]:
                p = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
                R['failure_diffs'][label] = {'exit_code': p.returncode, 'stdout': p.stdout[:4*1024**2].decode('utf8', 'replace'), 'truncated': len(p.stdout)>4*1024**2}
        R.update(state='failed or incomplete', error=repr(e)); save(); raise
