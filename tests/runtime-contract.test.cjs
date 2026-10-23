const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const runtime = fs.readFileSync(path.join(__dirname,'../src/js/90-runtime.js'),'utf8');
const health = fs.readFileSync(path.join(__dirname,'../src/js/05-data-health.js'),'utf8');
function liveContext() {
  const ctx = vm.createContext({ console, Date, Object, Array, Number });
  vm.runInContext(health + '\n' + runtime.slice(runtime.indexOf('function applyLive('),runtime.indexOf('async function loadData(')),ctx);
  return ctx;
}
test('paying off all liabilities replaces stale debts with a genuine zero', () => {
  const c=liveContext();
  const result=vm.runInContext('const s={assets:[{value_krw:100}],debt_krw:40,liabilities:[{amount_krw:40}]};applyLive(s,{liabilities:[],updated_at:"now"});JSON.stringify(s)',c);
  const s=JSON.parse(result);
  assert.equal(s.debt_krw,0);assert.equal(s.net_krw,100);assert.deepEqual(s.liabilities,[]);
});
test('empty news replaces previous stories without changing unrelated snapshots',()=>{
  const c=liveContext();
  const result=vm.runInContext('const s={checkpoint:{news:[{title:"old"}]}};applyLive(s,{news:[]});JSON.stringify(s)',c);
  assert.deepEqual(JSON.parse(result).checkpoint.news,[]);
});
test('unavailable liabilities preserve existing values',()=>{
  const c=liveContext();
  const result=vm.runInContext('const s={assets:[{value_krw:100}],debt_krw:40};applyLive(s,{liabilities:null});JSON.stringify(s)',c);
  assert.equal(JSON.parse(result).debt_krw,40);
});
function authContext() {
  const storage=()=>{const m=new Map();return {getItem:k=>m.get(k)||null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)};};
  const c=vm.createContext({sessionStorage:storage(),localStorage:storage(),location:{reload(){}},baseSnap:{},histText:"",console});
  vm.runInContext(runtime.slice(runtime.indexOf('let appPassphrase = null;'),runtime.indexOf('async function gate()')),c);
  return c;
}
test('default login survives reloads within the tab but does not persist across sessions',()=>{
  const c=authContext();vm.runInContext('retainPassword("sample",false)',c);
  assert.equal(c.sessionStorage.getItem('asset_pw'),'sample');
  assert.equal(c.localStorage.getItem('asset_pw'),null);
});
test('explicit remember and lock use reversible local state only',()=>{
  const c=authContext();vm.runInContext('retainPassword("sample",true)',c);
  assert.equal(c.localStorage.getItem('asset_remember_v2'),'1');
  vm.runInContext('lockDashboard()',c);
  assert.equal(c.localStorage.getItem('asset_pw'),null);
  assert.equal(c.sessionStorage.getItem('asset_pw'),null);
});
test('all production modules compile together without global name collisions',()=>{
  const folder=path.join(__dirname,'../src/js');
  const source=fs.readdirSync(folder).filter(f=>f.endsWith('.js')).sort().map(f=>fs.readFileSync(path.join(folder,f),'utf8')).join('\n');
  assert.doesNotThrow(()=>new vm.Script(source));
});

test('news retrieval time is independent from market publication',()=>{
  const c=liveContext();
  const result=vm.runInContext('const s={checkpoint:{}};applyLive(s,{news:[],us:[],updated_at:"2026-10-23T04:00:00Z",_fetched:{news:"2026-10-23T03:00:00Z"}});JSON.stringify(s)',c);
  const cp=JSON.parse(result).checkpoint;
  assert.equal(cp.news_at,'2026-10-23T03:00:00Z');
  assert.equal(cp.live_at,'2026-10-23T04:00:00Z');
});
