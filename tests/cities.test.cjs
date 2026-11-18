const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { dataHealth } = require('../src/js/05-data-health.js');
function context() {
  const elements = new Map();
  const get = id => { if(!elements.has(id)) elements.set(id,{innerHTML:'old',textContent:'',style:{display:'none'},dataset:{}}); return elements.get(id); };
  const c = vm.createContext({Date,Number,Math,console,esc:x=>String(x),ctShort:x=>x,
    document:{querySelector:()=>get('tab'),getElementById:get}});
  vm.runInContext(fs.readFileSync('src/js/05-data-health.js','utf8') + '\n' + fs.readFileSync('src/js/50-tabs.js','utf8'), c);
  return {c,get};
}
test('zero valid cities replaces old costs with a visible source error',()=>{
  const {c,get} = context();
  c.renderCities({cities:[],seoul:{},broken:['Test City'],fetched_at:'2026-11-18T01:00Z'},100);
  assert.equal(get('tab').style.display,'');
  assert.equal(get('ct-kpis').innerHTML,'');
  assert.equal(get('ct-table').innerHTML,'');
  assert.match(get('ct-status').textContent,/원본 계산 오류 1곳.*Test City/);
  assert.match(get('ct-bars-note').textContent,/계산 가능한 도시 자료가 없습니다/);
});
test('unavailable cities remain discoverable with an explanation',()=>{
  const {c,get} = context(); c.renderCities(null,100,{failed:true});
  assert.match(get('ct-status').textContent,/수집 실패/);
  assert.equal(get('tab').style.display,'');
});
test('a new publication cannot mark broken city formulas healthy',()=>{
  const now=Date.parse('2026-11-18T01:00Z');
  const h=dataHealth({}, {cities:{cities:[],broken:['City']},_fetched:{cities:new Date(now).toISOString()},_status:{cities:{state:'ok'}}},now);
  assert.equal(h.blocks.find(b=>b.key==='cities').state,'error');
});
