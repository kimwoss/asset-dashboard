const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const context = vm.createContext({
  esc: text => String(text).replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
});
vm.runInContext(fs.readFileSync('src/js/30-assets.js', 'utf8'), context);

const now = Date.parse('2026-11-07T00:20:00Z');
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

test('traditional interpretation can show calculated detail without generated prose', () => {
  const html = context.fortuneHtml({ layers: { month: '기해월', couple_action: '서로 물어봐요.',
    people: { woohyun: { daily: '정인', meaning: '자료 확인', month: '비견', hidden: ['식신'] } },
  } });
  for (const label of ['할머니 말씀', '전통 명리 해석', '정인', '지장간', '식신', '둘이 해볼 일'])
    assert.ok(html.includes(label));
});
