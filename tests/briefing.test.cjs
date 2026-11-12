const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const context = vm.createContext({
  esc: text => String(text).replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
});
for (const module of ['30-assets']) {
  vm.runInContext(fs.readFileSync(`src/js/${module}.js`, 'utf8'), context);
}

const now = Date.parse('2026-11-07T00:20:00Z');
test('canonical prose keeps mobile paragraphs without labels or local rewriting', () => {
  const html = context.fortuneHtml({style_version: 'daily-paragraphs-v1', ganzi: '병술',
    intro: '오늘의 계산된 인사', couple: '부부 첫 문단\n\n부부 둘째 문단',
    woohyun: {body: '원문 <첫> 문단\n\n원문 둘째 문단', money: '별도 항목은 만들지 않음'},
    kyuri: {body: '규리 첫 문단\n\n규리 둘째 문단'}, blessing: '축원',
  });
  assert.match(html, /원문 &lt;첫&gt; 문단<\/p><p class="fortune-body">원문 둘째 문단/);
  assert.match(html, /부부 첫 문단<\/p><p class="fortune-body">부부 둘째 문단/);
  assert.match(html, /우리 우현아/); assert.match(html, /우리 규리야/);
  assert.doesNotMatch(html, /별도 항목|돈 습관|<b>일터|오늘 말씀을 풀어낸 근거/);
});
test('briefing shows fact sources and distinguishes the KST day from UTC', () => {
  const result = context.briefingCard({
    generated_at: '2026-11-06T22:05:00Z', date_label: '11/7',
    briefing: { intro: '<hello>', weather: { text: '서울 오전 맑음' },
      market: { text: 'SCHD +0.40%', asof: '2026-11-06' } },
  }, now);
  assert.equal(result.sameDay, true);
  assert.match(result.html, /07:05 KST/);
  assert.match(result.html, /&lt;hello&gt;/);
  assert.match(result.html, /Open-Meteo/);
  assert.match(result.html, /2026-11-06 미국장 종가/);
});

test('old, missing and future morning data cannot masquerade as today', () => {
  for (const generated_at of ['2026-11-06T14:59:59Z', null, '2026-11-07T09:00:00Z']) {
    const result = context.briefingCard({ generated_at, date_label: '이전',
      greeting: '오래된 인사', weather: '오래된 날씨' }, now);
    assert.equal(result.sameDay, false);
    assert.doesNotMatch(result.html, /오래된/);
  }
});

test('legacy or missing copy cannot silently become another browser-generated fortune', () => {
  for (const data of [{layers: {people: {woohyun: {daily: '정인'}}}},
    {woohyun: {body: '과거 원문'}, layers: {people: {woohyun: {daily: '겁재'}}}}]) {
    const html = context.fortuneHtml(data);
    assert.match(html, /운세 원문을 아직 확인하지 못했어요/);
    assert.doesNotMatch(html, /과거 원문|나는 여기까지 할게|오늘의 십성/);
  }
  assert.match(context.fortuneHtml({intro: '명식 확인 필요'}), /명식 확인 필요/);
});
