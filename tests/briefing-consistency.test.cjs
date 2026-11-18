const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const health = fs.readFileSync('src/js/05-data-health.js', 'utf8');
const runtime = fs.readFileSync('src/js/90-runtime.js', 'utf8');
const assets = fs.readFileSync('src/js/30-assets.js', 'utf8');
function context() {
  const target = {innerHTML: ''};
  const ctx = vm.createContext({console, document: {getElementById: () => target},
    esc: value => String(value).replaceAll('<', '&lt;').replaceAll('>', '&gt;')});
  vm.runInContext(health + runtime.slice(runtime.indexOf('function applyLive('), runtime.indexOf('async function loadData(')) + assets, ctx);
  return {ctx, target};
}
test('mixed timestamp formats select the actual newest report', () => {
  const {ctx} = context();
  const result = vm.runInContext(`const snap = {checkpoint:{generated_at:'2026-11-18T06:00:00Z',summary:'new'}};
    applyLive(snap,{checkpoint:{generated_at:'2026-11-18T14:00:00+09:00',summary:'old'}});snap.checkpoint.summary`,ctx);
  assert.equal(result,'new');
});
test('future and invalid reports cannot replace the last valid report', () => {
  const {ctx} = context();
  for (const generated_at of ['not-a-date','2999-11-18T07:00:00+09:00']) {
    ctx.incoming = generated_at;
    assert.equal(vm.runInContext(`(() => {const snap={checkpoint:{generated_at:'2026-11-18T06:00:00Z',summary:'valid'}};
      applyLive(snap,{checkpoint:{generated_at:incoming,summary:'invalid'}});return snap.checkpoint.summary;})()`,ctx),'valid');
  }
});
test('an incomplete or older quote response preserves newer rows and their dates', () => {
  const {ctx} = context();
  const result = JSON.parse(vm.runInContext(`const snap={checkpoint:{us:[
    {name:'S&P500',asof:'2026-11-17',price:6000},{name:'SCHD',asof:'2026-11-17',price:30}]}};
    applyLive(snap,{us:[{name:'S&P500',asof:'2026-11-16',price:5000}]});
    applyLive(snap,{us:[]});JSON.stringify(snap.checkpoint.us)`,ctx));
  assert.deepEqual(result.map(row => row.price),[6000,30]);
});
test('yesterday morning is stale before the 25-hour TTL expires', () => {
  const {ctx} = context();
  const health = ctx.dataHealth({}, {checkpoint:{generated_at:'2026-11-17T07:00:00+09:00'}},Date.parse('2026-11-18T06:00:00+09:00'));
  assert.equal(health.blocks.find(row => row.key === 'checkpoint').state,'stale');
});
test('legacy KST timestamps use the same date and greeting as the morning report', () => {
  const {ctx} = context();
  const result = ctx.briefingCard({generated_at:'2026-11-18 07:00 KST',date_label:'11/18',
    greeting:'오늘의 인사',summary:'오늘의 해석',briefing:{intro:'고정 인사'}},Date.parse('2026-11-18T00:30Z'));
  assert.equal(result.sameDay,true);
  assert.match(result.html,/오늘의 인사/);
  assert.match(result.html,/오늘의 해석/);
  assert.doesNotMatch(result.html,/고정 인사/);
});
test('missing changes stay unavailable and each price shows its own date', () => {
  const {ctx,target} = context();
  ctx.renderCheckpoint({date_label:'11/18',us:[{name:'S&P500',price:6000,asof:'2026-11-17'},
    {name:'SCHD',price:30,asof:'2026-11-16'}],fear_greed:{score:30,label:'공포',vix:20}});
  assert.match(target.innerHTML,/2026-11-17 가격 기준/);
  assert.match(target.innerHTML,/2026-11-16 가격 기준/);
  assert.match(target.innerHTML,/모닝 리포트 11\/18 · 공포탐욕/);
  assert.doesNotMatch(target.innerHTML,/0\.00%|미국 지수 11-17 종가 기준/);
});
