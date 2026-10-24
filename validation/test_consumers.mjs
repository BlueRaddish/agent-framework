// Independent cache-route consumers of the actual workflow's GitHub expressions.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import YAML from 'yaml';
import {Parser, Lexer, Evaluator, data} from '@actions/expressions';

const workflow = YAML.parse(fs.readFileSync(new URL('../../../.github/workflows/ci-macos.yml', import.meta.url), 'utf8'));
const job = workflow.jobs['cli-product-tests'];
const fallback = job.steps.find(s => s.name === 'Download compiled test product');
const stages = ['node-products', 'peer-products', 'r2-products', 'parallel-products'];
// restore-layers is absent from this job. An irrelevant context output must not
// suppress the actual artifact fallback; it is not a fifth product source.
assert.ok(stages.every(id => job.steps.some(step => step.id === id)));
assert.ok(!job.steps.some(step => step.id === 'restore-layers'));
function context(value) {
  if (typeof value === 'string') return new data.StringData(value);
  return new data.Dictionary(...Object.entries(value).map(([key, v]) => ({key, value: context(v)})));
}
for (const hit of [null, ...stages, 'restore-layers']) {
  const expected = hit === null || hit === 'restore-layers';
  test(`GitHub fallback ${expected ? 'runs when only irrelevant outputs hit: ' + hit : 'does not run after ' + hit + ' hit'}`, () => {
    const values = {steps: Object.fromEntries([...stages, 'restore-layers'].map(s => [s, {outputs: {hit: s === hit ? 'true' : 'false'}}]))};
    const ast = new Parser(new Lexer(fallback.if).lex().tokens, Object.keys(values), []).parse();
    const result = new Evaluator(ast, context(values)).evaluate().coerceString();
    assert.equal(result, expected ? 'true' : 'false');
  });
}
