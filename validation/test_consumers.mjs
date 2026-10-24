// Independent cache-route consumers of the actual workflow's GitHub expressions.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import YAML from 'yaml';
import {Parser, Lexer, Evaluator, data} from '@actions/expressions';

const workflow = YAML.parse(fs.readFileSync(new URL('../../../.github/workflows/ci-macos.yml', import.meta.url), 'utf8'));
const job = workflow.jobs['cli-product-tests'];
const fallback = job.steps.find(s => s.name === 'Download compiled test product');
const stages = ['node-products', 'peer-products', 'restore-layers', 'r2-products', 'parallel-products'];
function context(value) {
  if (typeof value === 'string') return new data.StringData(value);
  return new data.Dictionary(...Object.entries(value).map(([key, v]) => ({key, value: context(v)})));
}
for (const hit of [null, ...stages]) {
  test(`GitHub fallback ${hit === null ? 'runs on all cache misses' : 'does not run after ' + hit + ' hit'}`, () => {
    const values = {steps: Object.fromEntries(stages.map(s => [s, {outputs: {hit: s === hit ? 'true' : 'false'}}]))};
    const ast = new Parser(new Lexer(fallback.if).lex().tokens, Object.keys(values), []).parse();
    const result = new Evaluator(ast, context(values)).evaluate().coerceString();
    assert.equal(result, hit === null ? 'true' : 'false');
  });
}
