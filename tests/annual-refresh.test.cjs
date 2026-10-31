const test=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const health=fs.readFileSync('src/js/05-data-health.js','utf8');
const runtime=fs.readFileSync('src/js/90-runtime.js','utf8');
function ctx(){const c=vm.createContext({console,Date,Intl});vm.runInContext(health+'\n'+runtime.slice(runtime.indexOf('function applyLive('),runtime.indexOf('async function loadData(')),c);return c;}
test('older live annual cache cannot overwrite a corrected snapshot',()=>{
 const c=ctx();const s=JSON.parse(vm.runInContext('const s={annual_flow:[{expense:200}],annual_flow_asof:"2026-10-31T15:10:00+09:00"};applyLive(s,{annual_flow:[{expense:100}],_fetched:{annual_flow:"2026-10-31T15:03:00+09:00"}});JSON.stringify(s)',c));
 assert.equal(s.annual_flow[0].expense,200);
});
test('newer annual read replaces values and the block source timestamp',()=>{
 const c=ctx();const s=JSON.parse(vm.runInContext('const s={annual_flow:[{expense:100}],updated_at:"2026-10-31 07:30 KST"};applyLive(s,{annual_flow:[{expense:200}],_fetched:{annual_flow:"2026-10-31T15:32:00+09:00"}});JSON.stringify(s)',c));
 assert.equal(s.annual_flow[0].expense,200);assert.equal(s.annual_flow_asof,'2026-10-31T15:32:00+09:00');
});
test('unknown live source time does not replace a known corrected snapshot',()=>{
 const c=ctx();const s=JSON.parse(vm.runInContext('const s={annual_flow:[{expense:200}],annual_flow_asof:"2026-10-31T15:10:00+09:00"};applyLive(s,{annual_flow:[{expense:100}]});JSON.stringify(s)',c));
 assert.equal(s.annual_flow[0].expense,200);
});
test('corrected missing-cost notes are never labelled as uncorrected shortfalls',()=>{
 const c=vm.createContext({console,Date,Intl});vm.runInContext(health+'\n'+fs.readFileSync('src/js/10-charts.js','utf8'),c);
 const note=c.annualFlowNote([{year:2024,note:'보정 추정 · 누락 고정비 복원'},{year:2022,note:'보정 추정 · 결혼 별도'}],'2026-10-31T15:32:00+09:00');
 assert.match(note,/보정 추정치/);assert.match(note,/결혼 관련/);assert.match(note,/15:32/);assert.doesNotMatch(note,/과소 집계/);
});
