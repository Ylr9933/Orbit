import assert from 'node:assert/strict';
import test from 'node:test';
import { csv, groupSteps, configDiff, outcome } from '../../src/web/src/features/benchmark/utils.ts';

test('CSV preserves zero/missing and neutralizes spreadsheet formulas', () => {
  const value = csv([['task', 'score'], ['=SUM(A1)', 0], ['missing', null], ['a,b"c', -2]]);
  assert(value.includes('"\'=SUM(A1)","0"'));
  assert(value.includes('"missing",""'));
  assert(value.includes('"a,b""c","-2"'));
});
test('trajectory pairing uses explicit call identity and keeps unpaired steps', () => {
  const step = (i, type, id) => ({ step_index: i, step_type: type, content: '', metadata: id ? { tool_call_id: id } : {} });
  const values = groupSteps([step(0, 'tool_call', 'a'), step(1, 'tool_result', 'b'), step(2, 'tool_result', 'a'), step(3, 'tool_call')]);
  assert.equal(values.length, 3);
  assert.equal(values[0].response.step_index, 2);
  assert.equal(values[1].response, undefined);
});
test('configuration diff and zero score do not disguise runtime failures', () => {
  assert.deepEqual(configDiff({ a: { model: 'old' } }, { a: { model: 'new' } }), [{ field: 'a.model', left: '"old"', right: '"new"' }]);
  assert.equal(outcome({ state: 'finished', score_valid: true, metrics: { score: 0 } }), '已评分');
  assert.equal(outcome({ state: 'finished', execution: 'failed', score_valid: false }), '执行失败');
});
