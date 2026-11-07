const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const context = vm.createContext({
  esc: text => String(text).replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
});
for (const module of ['29-fortune', '30-assets']) {
  vm.runInContext(fs.readFileSync(`src/js/${module}.js`, 'utf8'), context);
}

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
  for (const label of ['할머니 말씀', '오늘 말씀을 풀어낸 근거', '정인', '지장간', '식신', '우현에게', '원문'])
    assert.ok(html.includes(label));
});

test('the fallback in the screenshot becomes two specific letters and a shared conversation', () => {
  const body = type => `할미가 보니 오늘 乙酉 일진이 일간 甲(木)에 ${type} 기운으로 닿는구나. 그 기운 믿고 차분히 하루를 꾸리면 된단다. � 오늘의 한 수: 챙겨 보거라.`;
  const html = context.fortuneHtml({
    ganzi: '乙酉 을유', zodiac: '닭', intro: '닭의 날 날이구먼',
    woohyun: { body: body('겁재') }, kyuri: { body: body('정인') },
  });
  assert.match(html, /나는 여기까지 할게/);
  assert.match(html, /내가 이해한 기준이 이게 맞을까/);
  assert.match(html, /둘이 앉으면/);
  assert.match(html, /좋은 마음으로 맡았다가/);
  assert.match(html, /누군가에게 물어봤으면/);
  assert.doesNotMatch(html, /�|날 날|그 기운 믿고|한국천문연구원/);
});

test('a supporting type or relationship changes the follow-up without guessing an event', () => {
  const a = context.fortuneLetter('kyuri', {}, { daily: '정인', hidden: ['상관'] });
  const b = context.fortuneLetter('kyuri', {}, { daily: '정인', hidden: ['정재'] });
  const c = context.fortuneLetter('kyuri', {}, { daily: '정인', relationship_focus: '가까운 관계 자리' });
  assert.equal(a.paragraphs[0], b.paragraphs[0]);
  assert.notEqual(a.paragraphs[1], b.paragraphs[1]);
  assert.match(c.paragraphs[1], /약속이 어긋나면/);
});

test('same daily type still gives different advice to each partner', () => {
  for (const daily of ['비견', '겁재', '식신', '상관', '편재', '정재', '편관', '정관', '편인', '정인']) {
    const a = context.fortuneLetter('woohyun', {}, { daily });
    const b = context.fortuneLetter('kyuri', {}, { daily });
    assert.notEqual(a.paragraphs[0], b.paragraphs[0]);
  }
  assert.equal(context.fortuneLetter('woohyun', { body: '아마 겁재라는 말이 나왔대.' }), null);
});
