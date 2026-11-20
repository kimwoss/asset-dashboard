const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {refreshGap}=require('../src/js/06-refresh-policy.js');
const {quoteSourceLabel,dataHealth}=require('../src/js/05-data-health.js');
test('briefing polls at 30 seconds during KR and US openings, across DST',()=>{
  for(const t of ['2026-11-20T00:00:01Z','2026-11-20T14:30:01Z','2026-07-20T13:30:01Z'])assert.equal(refreshGap(Date.parse(t)),30000);
  assert.equal(refreshGap(Date.parse('2026-11-20T00:00:01Z'),'overview'),60000);
  assert.equal(refreshGap(Date.parse('2026-11-21T12:00:00Z')),60000);
});
test('KB Friday window accelerates polling before the market opens',()=>{
  assert.equal(refreshGap(Date.parse('2026-11-19T23:00:01Z')),30000);
  assert.equal(refreshGap(Date.parse('2026-11-19T23:00:01Z'),'overview'),60000);
});
test('actual trade time, source and pending/delayed states remain visible',()=>{
  const label=quoteSourceLabel({price_at:'2026-11-20T09:31:00-05:00',price_kind:'intraday',source:'Yahoo Finance',quote_state:'delayed'});
  assert.match(label,/23:31/);assert.match(label,/장중/);assert.match(label,/시세 지연/);
  assert.match(quoteSourceLabel({asof:'2026-11-19',quote_state:'awaiting'}),/개장 후 시세 대기/);
});
function context(){
  const c=vm.createContext({console,Date,Object,Array,Number});
  const health=fs.readFileSync('src/js/05-data-health.js','utf8'),runtime=fs.readFileSync('src/js/90-runtime.js','utf8');
  vm.runInContext(health+runtime.slice(runtime.indexOf('function applyLive('),runtime.indexOf('async function loadData(')),c);
  return c;
}
test('old same-day ticks cannot replace a later opening quote',()=>{
  const c=context();
  const got=vm.runInContext(`const s={checkpoint:{us:[{name:'SCHD',price:36,asof:'2026-11-20',price_at:'2026-11-20T14:32:00Z'}]}};applyLive(s,{us:[{name:'SCHD',price:35,asof:'2026-11-20',price_at:'2026-11-20T14:30:00Z'}]});s.checkpoint.us[0].price`,c);
  assert.equal(got,36);
});
test('fast KB quote updates property, gross and net together without an old snapshot regression',()=>{
  const c=context();
  const got=JSON.parse(vm.runInContext(`const s={assets:[{name:'A',category:'부동산',value_krw:100,asof:'2026-11-13'}],debt_krw:40};applyLive(s,{real_estate:{assets:[{name:'A',category:'부동산',value_krw:110,asof:'2026-11-20'}]}});applyLive(s,{real_estate:{assets:[{name:'A',category:'부동산',value_krw:90,asof:'2026-11-13'}]}});JSON.stringify(s)`,c));
  assert.equal(got.assets[0].value_krw,110);assert.equal(got.gross_krw,110);assert.equal(got.net_krw,70);
});
test('successful retrieval never makes pending KB publication look up to date',()=>{
  const now=Date.parse('2026-11-20T00:00:00Z');
  const h=dataHealth({}, {real_estate:{assets:[{asof:'2026-11-13'}],pending:['A'],errors:[]},_fetched:{real_estate:new Date(now).toISOString()}},now);
  assert.equal(h.blocks.find(b=>b.key==='real_estate').state,'stale');
});

test('a transient connection error preserves the last publication without renewing its time',async()=>{
  const health=fs.readFileSync('src/js/05-data-health.js','utf8'),runtime=fs.readFileSync('src/js/90-runtime.js','utf8');
  let fail=false;
  const payload={updated_iso:'2026-11-20T00:02:00Z',real_estate:{assets:[{name:'A',value_krw:110,asof:'2026-11-20'}]}};
  const c=vm.createContext({console:{warn(){}},Date,structuredClone,AbortSignal,decryptEnvelope:async text=>text,fetch:async()=>{if(fail)throw Error('network');return {ok:true,text:async()=>JSON.stringify(payload)}}});
  vm.runInContext(health+runtime.slice(runtime.indexOf('const LIVE_URL ='),runtime.indexOf('function applyLive(')),c);
  const first=await c.loadLive('demo');fail=true;const last=await c.loadLive('demo');
  assert.equal(last.real_estate.assets[0].value_krw,first.real_estate.assets[0].value_krw);
  assert.equal(last.updated_iso,first.updated_iso);assert.equal(last._connection_error,true);
});
