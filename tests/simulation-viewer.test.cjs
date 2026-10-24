const test=require('node:test');
const assert=require('node:assert/strict');
const {simulationYearFacts}=require('../src/js/66-simulation-viewer.js');
test('year facts keep zeros and separate expenses from income',()=>{
 assert.deepEqual(simulationYearFacts({net:0,real_net:0,spend:10,medical:2,pension:3,retire_income:4}),{nominal:0,real:0,expenses:12,income:7});
});
test('older payloads never turn missing income into a false zero',()=>{
 assert.equal(simulationYearFacts({pension:0}).income,null);
 assert.equal(simulationYearFacts({spend:10,medical:null}).expenses,null);
});
test('negative assets stay negative and non-finite values stay unavailable',()=>{
 assert.equal(simulationYearFacts({net:-100}).nominal,-100);
 assert.equal(simulationYearFacts({real_net:NaN}).real,null);
});
