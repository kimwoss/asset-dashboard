const test = require('node:test');
const assert = require('node:assert/strict');
const { dataTime, dataAge, dataHealth, presentValue } = require('../src/js/05-data-health.js');
test('legacy timestamps always use KST', () => {
  assert.equal(dataTime('2026-10-23 14:05 KST'), Date.parse('2026-10-23T14:05:00+09:00'));
  assert.equal(dataTime('2026-10-23 14:05'), Date.parse('2026-10-23T14:05:00+09:00'));
  assert.equal(dataAge('2026-10-23 14:05', Date.parse('2026-10-23T05:35Z')), 30);
  assert.equal(dataTime('not a timestamp'), null);
});
test('new publication does not conceal old or failed data', () => {
  const now = Date.parse('2026-10-23T14:00:00+09:00');
  const live = { updated_iso: new Date(now).toISOString(), financial: {}, spending: {},
    _fetched: { financial: '2026-10-23T13:59:00+09:00', spending: '2026-10-22T13:00:00+09:00' },
    _status: { financial: { state: 'error' } } };
  const h = dataHealth({}, live, now);
  assert.equal(h.blocks.find(b => b.key === 'financial').state, 'error');
  assert.equal(h.blocks.find(b => b.key === 'spending').state, 'stale');
  assert.equal(h.state, 'attention');
});
test('empty arrays and zero are present; null is unavailable', () => {
  assert.equal(presentValue({ liabilities: [] }, 'liabilities'), true);
  assert.equal(presentValue({ total: 0 }, 'total'), true);
  assert.equal(presentValue({ liabilities: null }, 'liabilities'), false);
  assert.equal(presentValue({}, 'liabilities'), false);
});
test('missing metadata never earns a fresh badge', () => {
  const h = dataHealth({}, { financial: {}, updated_iso: new Date().toISOString() });
  assert.equal(h.blocks.find(b => b.key === 'financial').state, 'unknown');
  assert.equal(dataHealth({}, null).state, 'snapshot');
});
