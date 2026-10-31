const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('src/js/67-account-moves.js','utf8');
function render(fin) {
 const context = {esc:s=>String(s).replaceAll('<','&lt;').replaceAll('>','&gt;')};
 vm.createContext(context);vm.runInContext(source,context);
 return context.accountMovesHtml(fin);
}
test('old encrypted payloads show a truthful pending state',()=>{
 const html=render({holdings:[]});assert.match(html,/준비 중/);assert.doesNotMatch(html,/0\.00%/);
});
test('account movements show all four horizons and never fabricate missing returns',()=>{
 const html=render({account_performance:{accounts:[{owner:'가상 사용자',account:'<ISA>',current_krw:12300,periods:{d1:{pct:-2,delta_krw:-251,base_dates:['2026-10-29']},w1:{pct:0,delta_krw:0}}}]}});
 assert.match(html,/&lt;ISA&gt;/);assert.match(html,/−251원/);assert.match(html,/-2\.00%/);assert.match(html,/0\.00%/);
 assert.match(html,/1일 전/);assert.match(html,/1주 전/);assert.match(html,/1개월 전/);assert.match(html,/1년 전/);
 assert.equal((html.match(/account-unavailable/g)||[]).length,2);
});
test('the briefing owns the replacement and no global retirement teaser remains',()=>{
 const html=fs.readFileSync('src/index.template.html','utf8');
 const start=html.indexOf('id="tab-checkpoint"');
 assert.ok(html.indexOf('id="account-moves"',start)>start);
 assert.doesNotMatch(html,/id="simulation-drawer"/);
});
