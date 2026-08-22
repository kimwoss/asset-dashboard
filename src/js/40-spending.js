/* ---- 월간 생활비 (시각화 탭 '상세항목별 지출 금액') ---- */
const SP_COLORS = {
  "생활": "#3182F6", "외식": "#FF6B6B", "교통": "#12B886", "쇼핑": "#F76707",
  "여행": "#7048E8", "미용": "#E64980", "세금": "#868E96", "주거": "#0CA678",
  "경조": "#FAB005", "가족": "#4C6EF5", "모임": "#15AABF", "기타": "#ADB5BD",
  "자기계발": "#20C997", "건강": "#FA5252", "기부": "#BE4BDB",
  "용돈": "#FD7E14", "보험": "#5C7CFA", "구독": "#22B8CF",
  // 표준 카테고리는 가계부 이름을 그대로 쓴다 — 위 색이 그대로 이어진다. 예외 하나만:
  "세금·연금": "#868E96",
};
const spColor = (name, i) => SP_COLORS[name] || `hsl(${(i * 47) % 360} 62% 55%)`;

/* ── 지금(가계부) vs 은퇴(계획)을 같은 잣대로 놓기 위한 표준 카테고리 ──────────
   두 데이터는 분류 체계가 아니라 '포함 범위'가 다르다. 그래서 이름만 맞추면 안 되고,
   차이의 성격(생활 방식이냐 / 구조 전환이냐 / 제도 전환이냐)까지 갈라 보여줘야
   "은퇴하면 정말 2배 써야 하나?"에 정직하게 답할 수 있다.
   cur=시각화 탭 카테고리, ret=참조.연간 생활비 항목(월·연·생활비세부 모두). */
const KIND_META = {
  생활: { icon: "🟢", label: "생활 방식 차이", desc: "지금도 쓰고 은퇴 후에도 쓰는 돈 — 순수 비교 대상" },
  구조: { icon: "🟡", label: "구조 전환", desc: "전세 거주(관리비+대출이자) → 월세 환산 가정. 씀씀이가 아니라 모델 가정" },
  제도: { icon: "🔵", label: "제도 전환", desc: "급여 원천공제 → 지역가입. 지금도 내고 있지만 가계부엔 안 잡히는 돈" },
};
/* 기준선은 '가계부(시각화 탭)의 카테고리'다 — 실제로 매달 그렇게 적고 있으니 그게 진실이다.
   은퇴 계획이 더 잘게 쪼개져 있어도(식비·자기계발·건강…) 가계부의 '생활' 한 칸에 함께
   담기는 것들은 '생활'로 접어서 비교한다. 반대로 하면 식비 89→50(감소), 자기계발 0→20
   같은 허깨비 증감이 생겨 비교가 무의미해진다. */
const STD_CATS = [
  { key: "생활",    kind: "생활", cur: ["생활"],  ret: ["식비", "자기계발", "건강", "건강검진비"] },
  { key: "외식",    kind: "생활", cur: ["외식"],  ret: ["외식"] },
  { key: "주거",    kind: "구조", cur: ["주거"],  ret: ["주거비", "주거"] },
  { key: "교통",    kind: "생활", cur: ["교통"],  ret: ["교통"] },
  { key: "여행",    kind: "생활", cur: ["여행"],  ret: ["여행"] },
  { key: "쇼핑",    kind: "생활", cur: ["쇼핑"],  ret: ["쇼핑"] },
  { key: "미용",    kind: "생활", cur: ["미용"],  ret: ["미용"] },
  { key: "가족",    kind: "생활", cur: ["가족"],  ret: ["가족 (할머니)", "가족 (부모님)", "부모님 건강검진비"] },
  { key: "경조",    kind: "생활", cur: ["경조"],  ret: ["경조"] },
  { key: "용돈",    kind: "생활", cur: ["용돈"],  ret: ["개인용돈"] },
  { key: "보험",    kind: "생활", cur: ["보험"],  ret: ["국내보험(종합/실손)", "해외여행자보험"] },
  { key: "세금·연금", kind: "제도", cur: ["세금"], ret: ["국민연금", "건강보험료", "재산세"] },
  { key: "기부",    kind: "생활", cur: ["기부"],  ret: ["기부"] },
  // 은퇴 계획에는 대출 예산이 없다 — 그때는 다 갚는다는 전제라 ret가 비어 있는 게 맞다.
  // 그래서 이 줄은 '은퇴하면 사라지는 부담'으로 읽힌다(감소 = 초록).
  { key: "대출",    kind: "구조", cur: ["대출"],  ret: [] },
  { key: "기타",    kind: "생활", cur: ["기타", "구독", "모임"], ret: [] },
  // 예비비는 은퇴 계획에만 있는 줄이다 — 지금은 쓰고 남으면 그만이지만, 근로소득이 끊기면
  // 예상 못 한 지출을 받아 줄 완충이 따로 있어야 한다. 한때 가계부의 기타·구독·모임과
  // 같은 칸에 접어 뒀는데, 성격이 달라 '새로 생기는 부담'이 안 보였다.
  { key: "예비비",  kind: "구조", cur: [],        ret: ["예비비"] },
];

/* 거주(전세) 조달 대출의 월 이자 — 지금 '집에 사는 값'의 실체.
   가계부의 주거 27만은 관리비뿐이고, 전세보증금을 마련한 대출 이자는 '대출' 항목에 묶여
   생활비에서 빠져 있다. 그대로 두면 은퇴(월세 200만)와 비교할 때 주거비가 부풀려 보인다.
   ★연도별자산에서 target='전세보증금'인 대출만 골라, 이름에 박힌 실제 금리로 계산한다
   (하드코딩 없음 — 상환하거나 갈아타면 자동 반영). 원금 상환은 저축이라 제외, 이자만. */
function jeonseInterest(liabs) {
  const rows = (liabs || []).filter(l => l.kind === "loan" && l.target === "전세보증금");
  let won = 0; const parts = [];
  for (const l of rows) {
    const m = /([\d.]+)\s*%/.exec(l.name || "");
    if (!m) continue;
    const rate = parseFloat(m[1]) / 100;
    const monthly = l.amount_krw * rate / 12;
    won += monthly;
    parts.push({ name: l.name, amount: l.amount_krw, rate: parseFloat(m[1]), monthly });
  }
  return { monthly: Math.round(won), parts, principal: rows.reduce((s, l) => s + l.amount_krw, 0) };
}

/* 양쪽을 표준 카테고리로 접는다. 어느 쪽도 금액을 버리지 않는다 —
   매핑에 없는 항목은 '기타'로 떨어뜨리고 이름을 unmapped로 넘겨 화면에 경고한다.
   (시트를 또 재정리해도 합계가 틀어지지 않고, 무엇이 빠졌는지 즉시 보인다)
   housingInterest: 지금 사는 집(파크하비오 오피스텔)의 보증금을 마련한 대출의 월 이자.
   가계부는 이걸 '대출'에 적지만, 은퇴 계획의 '주거비'는 월세다 — 성격이 같은 돈이
   서로 다른 칸에 있으면 주거를 27만 vs 230만으로 비교하게 돼 완전히 다른 그림이 된다.
   그래서 '대출'에서 덜어 '주거'로 옮긴다. 더하는 게 아니라 옮기는 것이라 총액은 그대로다
   (예전엔 대출을 통째로 빼 두고 주거에 이자를 얹었는데, 대출을 다시 넣자 이중계상이 됐다). */
function buildStdCompare(sp, re, cn, housingInterest) {
  if (!re || !re.avg_monthly) return null;
  const curOf = {}, retOf = {}, unmapped = [];
  for (const c of STD_CATS) { curOf[c.key] = 0; retOf[c.key] = 0; }
  const find = (name, side) => (STD_CATS.find(c => c[side].includes(name)) || {}).key;

  // 현재 — 마감 월 평균
  for (const c of sp.categories) {
    const v = c.values.slice(0, cn).reduce((a, b) => a + b, 0) / cn;
    if (v <= 0) continue;
    const k = find(c.name, "cur");
    if (k) curOf[k] += v; else { curOf["기타"] += v; unmapped.push("가계부:" + c.name); }
  }
  // 은퇴 — 월 항목(단, '생활비' 덩어리는 세부로 대체) + 생활비 세부 + 연 항목/12
  const living = re.living_detail || [];
  const lumpName = re.living_label || "생활비";
  const add = (name, amt) => {
    if (!(amt > 0)) return;
    const k = find(name, "ret");
    if (k) retOf[k] += amt; else { retOf["기타"] += amt; unmapped.push("은퇴:" + name); }
  };
  let lump = 0;
  for (const it of (re.monthly_items || [])) {
    if (it.name === lumpName && living.length) { lump = it.amount; continue; }
    add(it.name, it.amount);
  }
  for (const it of living) add(it.name, it.amount);
  // 시트의 '생활비' 합계와 세부 합계가 어긋나면(반올림·수기 입력) 차액을 기타로 흡수해 총액 보존
  const gap = lump - living.reduce((s, x) => s + x.amount, 0);
  if (Math.abs(gap) > 0) retOf["기타"] += gap;
  for (const it of (re.annual_items || [])) add(it.name, it.amount / 12);

  // 거주 조달 대출 이자를 '대출' → '주거'로 이동. 가계부에 잡힌 대출을 넘겨 옮길 수는
  // 없으므로 실제 있는 만큼만 옮긴다(원금까지 주거로 넘어가지 않게 하는 안전장치이기도 하다).
  const moved = Math.min(Math.max(0, housingInterest || 0), curOf["대출"] || 0);
  if (moved > 0) { curOf["대출"] -= moved; curOf["주거"] += moved; }

  const rows = STD_CATS
    .map(c => ({ name: c.key, kind: c.kind, avg: Math.round(curOf[c.key]), ret: Math.round(retOf[c.key]) }))
    .filter(x => x.avg > 0 || x.ret > 0)
    // 지금 많이 쓰는 순. 격차 큰 순으로도 놔 봤는데, 몇 만원짜리 항목이 증가폭만 크다고
    // 맨 위로 올라와 '우리 살림의 무게'와 순서가 어긋났다. 증가폭은 오른쪽 숫자로 읽는다.
    .sort((a, b) => (b.avg - a.avg) || (b.ret - a.ret));
  const byKind = {};
  for (const x of rows) byKind[x.kind] = (byKind[x.kind] || 0) + (x.ret - x.avg);
  // 합계는 행별 반올림 전 값으로 — 14행을 각각 반올림해 더하면 원본과 몇 원씩 어긋나
  // 헤드라인이 862/863처럼 널뛴다 (은퇴 862.5만이 내림돼 보이던 문제).
  return {
    rows, byKind, unmapped, moved: Math.round(moved),
    totAvg: Math.round(Object.values(curOf).reduce((s, v) => s + v, 0)),
    totRet: Math.round(Object.values(retOf).reduce((s, v) => s + v, 0)),
  };
}

/* 브릿지(폭포) — 현재 월평균에서 은퇴 월평균까지 무엇이 얼마나 보태는지.
   "2배 써야 한다"가 아니라 "구조·제도가 대부분이고 씀씀이 상향은 이만큼"을 읽게 한다. */
function renderBridge(from, to, byKind, jeonse, moved) {
  const steps = Object.keys(KIND_META)
    .filter(k => Math.round((byKind[k] || 0) / 1e4) !== 0)
    .map(k => ({ kind: k, v: byKind[k] }));
  const hi = Math.max(from, to) * 1.06;
  const pctW = v => Math.max(0.6, Math.abs(v) / hi * 100);
  let acc = from;
  const rowOf = (label, icon, val, base, cls, strong) => {
    const left = Math.min(base, base + val) / hi * 100;
    return `<div class="brg-row">
      <div class="brg-name">${icon ? `<span class="kind-dot">${icon}</span>` : ""}${esc(label)}</div>
      <div class="brg-track">
        <div class="brg-fill ${cls}" style="left:${left}%;width:${pctW(val)}%"></div>
      </div>
      <div class="brg-v ${strong ? "brg-strong" : ""}">${strong ? fmtMan(val) : (val > 0 ? "+" : "−") + manNum(Math.abs(val)) + "만"}</div>
    </div>`;
  };
  let h = rowOf("지금 월평균", "", from, 0, "brg-base", true);
  for (const s of steps) {
    h += rowOf(KIND_META[s.kind].label, KIND_META[s.kind].icon, s.v, acc, s.v > 0 ? "brg-up" : "brg-down", false);
    acc += s.v;
  }
  h += rowOf("은퇴 월평균", "", to, 0, "brg-base brg-end", true);
  document.getElementById("sp-bridge").innerHTML = h;

  const big = steps.slice().sort((a, b) => b.v - a.v)[0];
  const lifePct = to > from ? Math.round((byKind["생활"] || 0) / (to - from) * 100) : 0;
  const jLoans = (jeonse && jeonse.parts || []).map(p => `${Math.round(p.amount / 1e8 * 10) / 10}억@${p.rate}%`).join(" + ");
  const jp = moved
    ? `🟡 <b>주거</b>는 <b>관리비 + 거주 조달 대출 이자 ${manNum(moved)}만</b>(${jLoans})으로 잡았습니다. `
      + `그 이자는 가계부에서 '대출'에 적히지만 은퇴 계획의 주거비는 월세라, 같은 성격끼리 `
      + `놓으려고 대출에서 <b>옮겨</b> 왔습니다(더한 게 아니라 옮긴 것이라 합계는 그대로). `
      + `원금 상환은 저축이라 뺐습니다.<br>`
    : "";
  document.getElementById("sp-bridge-note").innerHTML = big
    ? `가장 큰 요인은 <b>${KIND_META[big.kind].label}</b> (${big.v > 0 ? "+" : "−"}${manNum(Math.abs(big.v))}만/월). `
      + `늘어나는 ${fmtMan(to - from)} 중 순수한 생활 수준 상향은 <b>${lifePct}%</b>이고, 나머지는 구조·제도 전환입니다.<br>`
      + jp
      + `🔵 건강보험·국민연금은 지금도 급여에서 빠져나가지만 가계부엔 기록되지 않습니다.`
    : "";
}
// 만원 반올림 — Math.round(-2230/1e4)는 -0이라 그대로 찍으면 "-0"이 된다
const manNum = v => { const r = Math.round(v / 1e4); return (r === 0 ? 0 : r).toLocaleString(); };

/* 월별 스택 막대 — 막대 위에 합계, 모든 달 라벨 (마우스오버 없이 읽히게).
   음수 항목(환급·정정)은 쌓지 않고 합계에만 반영한다. 스택 막대에 음수를 넣으면
   기준선이 무너져 다른 달과 높이를 비교할 수 없게 되기 때문. */
// opts.onPick(i)를 주면 달을 고를 수 있다 — 아래 '카테고리 비중' 도넛이 그 달로 바뀐다.
// 하이라이트·클릭판은 세그먼트보다 먼저 그려 뒤에 깔린다. 위에 덮으면 세그먼트 툴팁이 죽는다.
function stackedBars(container, months, series, totals, opts) {
  const { onPick = null, selected = -1 } = opts || {};
  container.innerHTML = "";
  const n = months.length;
  if (!n) { container.textContent = "데이터가 아직 없습니다."; return; }
  const W = Math.min(container.clientWidth || 900, 1000), H = 300;
  const m = { l: 52, r: 12, t: 30, b: 30 };
  const hi = Math.max(...totals, 1) * 1.12;
  const bw = (W - m.l - m.r) / n;
  const barW = Math.min(46, bw * 0.62);
  const xc = i => m.l + bw * (i + 0.5);
  const ys = v => m.t + (H - m.t - m.b) * (1 - v / hi);
  const svg = el("svg", { width: "100%", viewBox: `0 0 ${W} ${H}` });

  for (let g = 0; g <= 3; g++) {
    const v = hi * g / 3, y = ys(v);
    el("line", { x1: m.l, x2: W - m.r, y1: y, y2: y, stroke: "var(--grid)", "stroke-width": 1 }, svg);
    el("text", { x: m.l - 8, y: y + 4, "text-anchor": "end", "font-size": 11, fill: "var(--ink-muted)" }, svg)
      .textContent = manNum(v);
  }

  if (onPick) {
    for (let i = 0; i < n; i++) {
      const col = el("rect", { x: m.l + bw * i + 2, y: m.t - 22, width: bw - 4,
                               height: H - m.t - m.b + 24, rx: 8,
                               fill: i === selected ? "var(--grid)" : "transparent" }, svg);
      col.style.cursor = "pointer";
      col.addEventListener("click", () => onPick(i));
    }
  }

  const base = new Array(n).fill(0);
  for (const [si, s] of series.entries()) {
    for (let i = 0; i < n; i++) {
      const v = Math.max(0, s.values[i] || 0);
      if (v <= 0) continue;
      const y0 = ys(base[i]), y1 = ys(base[i] + v);
      const r = el("rect", { x: xc(i) - barW / 2, y: y1, width: barW, height: Math.max(0.6, y0 - y1),
                             fill: s.color, "fill-opacity": 0.92 }, svg);
      if (onPick) { r.style.cursor = "pointer"; r.addEventListener("click", () => onPick(i)); }
      r.addEventListener("mousemove", ev => showTip(ev,
        `<b>${months[i].label}</b> · ${s.label}<br>${fmtWon(s.values[i])}` +
        `<br><span style="color:var(--ink-muted)">합계 ${fmtWon(totals[i])} 중 ` +
        `${totals[i] ? (s.values[i] / totals[i] * 100).toFixed(1) : 0}%</span>`));
      r.addEventListener("mouseleave", hideTip);
      base[i] += v;
    }
  }

  for (let i = 0; i < n; i++) {
    el("text", { x: xc(i), y: ys(base[i]) - 8, "text-anchor": "middle", "font-size": 11.5,
                 "font-weight": 700, fill: "var(--ink-1)" }, svg)
      .textContent = manNum(totals[i]);
    el("text", { x: xc(i), y: H - 9, "text-anchor": "middle", "font-size": 11,
                 "font-weight": i === selected ? 700 : 400,
                 fill: i === selected ? "var(--ink-1)" : "var(--ink-muted)" }, svg)
      .textContent = months[i].label;
  }
  el("text", { x: m.l - 8, y: m.t - 12, "text-anchor": "end", "font-size": 10, fill: "var(--ink-muted)" }, svg)
    .textContent = "만원";
  container.appendChild(svg);

  const lg = document.createElement("div"); lg.className = "legend";
  for (const s of series) {
    const sp = document.createElement("span"); sp.style.setProperty("--sw", s.color);
    sp.textContent = s.label; lg.appendChild(sp);
  }
  container.appendChild(lg);
}

function renderSpending(sp, liabs) {
  const tabBtn = document.querySelector('.tab[data-tab="spending"]');
  if (!sp || !sp.categories || !sp.categories.length) { if (tabBtn) tabBtn.style.display = "none"; return; }

  const months = sp.months.map(k => ({ key: k, label: `${+k.slice(5)}월` }));
  const n = months.length;
  const series = sp.categories.map((c, i) => ({ label: c.name, color: spColor(c.name, i), values: c.values }));
  const totals = sp.total;

  // KPI — 진행 중인 달은 평균에서 뺀다 (반쪽 달이 평균을 끌어내린다).
  //   마감 개월 수는 서버가 sp.closed로 알려준다. '마지막 달 = 진행 중'으로 짐작하면
  //   달이 바뀐 직후(예: 8월 1일, 8월은 아직 빈 달이라 잘려나감) 이미 마감된 7월까지
  //   평균에서 빠진다. 구버전 데이터 호환으로만 옛 방식을 남긴다.
  const nClosed = Number.isInteger(sp.closed) ? Math.min(sp.closed, n) : n - 1;
  const closed = totals.slice(0, nClosed);
  const cn = Math.max(1, closed.length);  // 마감 월 수 (1월뿐이면 그 달을 평균으로)
  const avg = closed.length ? closed.reduce((a, b) => a + b, 0) / closed.length : totals[n - 1];
  const inProgress = nClosed < n;         // 마지막 달이 아직 진행 중인가
  const ytd = totals.reduce((a, b) => a + b, 0);
  const cur = totals[n - 1];
  const dv = avg ? (cur - avg) / avg * 100 : 0;
  const curTag = inProgress ? " · 진행 중" : " · 마감";
  let cards = kpiCard(`${months[n - 1].label} 생활비`, fmtMan(cur),
    closed.length ? `<span class="${dv <= 0 ? "delta-up" : "delta-down"}">${dv >= 0 ? "▲" : "▼"} ${Math.abs(dv).toFixed(0)}%</span> vs 월평균${curTag}` : "진행 중", true);
  cards += kpiCard("월평균", fmtMan(avg), `${months[0].label}~${months[cn - 1].label} 마감 ${closed.length}개월`);
  cards += kpiCard(`${sp.year}년 누적`, fmtMan(ytd), `${n}개월 합계`);
  document.getElementById("sp-kpis").innerHTML = cards;

  // 카테고리 비중 — 고른 달과 월평균을 나란히. 탭으로 갈아끼우면 서로 비교가 안 됐다.
  const row = document.getElementById("sp-donuts");
  const noteEl = document.getElementById("sp-donut-note");
  const donutOf = (title, caption, pick) => {
    const slices = sp.categories.map((c, i) => ({ label: c.name, value: Math.max(0, pick(c)), color: spColor(c.name, i) }))
      .filter(s => s.value > 0).sort((a, b) => b.value - a.value);
    donut(donutCell(row), {
      title, caption, slices, fmt: fmtMan, centerLabel: "생활비",
      center: slices.reduce((s, x) => s + x.value, 0),
      legendValue: true,                                  // 범례를 %가 아닌 금액으로
      annotateTop: 3, annFmt: v => manNum(v) + "만",       // 상위 3개는 링 위에 값 병기
    });
  };
  // 왼쪽 도넛은 '이번 달' 고정이 아니라 위 막대에서 고른 달을 따라간다.
  // 지난달 구성을 보려고 시트를 다시 여는 게 이 화면에서 제일 잦은 이탈이었다.
  let selMonth = n - 1;

  const paintDonuts = () => {
    row.innerHTML = "";
    const isCur = selMonth === n - 1;
    donutOf(months[selMonth].label, isCur && inProgress ? "진행 중" : "마감",
            c => c.values[selMonth] || 0);
    donutOf("월평균", `${months[0].label}~${months[cn - 1].label} 마감 ${cn}개월`,
            c => c.values.slice(0, cn).reduce((a, b) => a + b, 0) / cn);
    noteEl.innerHTML =
      "월평균은 마감된 달만 반영 — 가운데 금액이 '보통 달' 기준선입니다."
      + `<br>위 막대에서 달을 누르면 왼쪽 도넛이 그 달로 바뀝니다.`
      + (isCur ? "" : ` 지금 <b>${months[selMonth].label}</b>을 보는 중 —`
                    + ` <button type="button" class="linkish" id="sp-donut-reset">`
                    + `${months[n - 1].label}로 돌아가기</button>`);
    const reset = document.getElementById("sp-donut-reset");
    if (reset) reset.addEventListener("click", () => pick(n - 1));
  };

  const paintBars = () => stackedBars(document.getElementById("sp-bars"), months, series, totals,
                                      { selected: selMonth, onPick: pick });

  function pick(i) {
    if (i === selMonth) return;
    selMonth = i;
    paintBars();
    paintDonuts();
  }

  paintBars();
  paintDonuts();

  // ── 지금 vs 은퇴: 표준 카테고리로 정규화해 비교 ────────────────────────────
  // 두 데이터는 분류가 아니라 '포함 범위'가 다르다. 가계부는 통장에서 나간 돈만 적히니
  // 급여에서 원천공제되는 건보·국민연금이 안 보이고, 전세라 월세도 0이다. 반면 은퇴 계획은
  // 살아가는 데 드는 모든 돈을 담는다. 그래서 이름만 맞추면 안 되고 성격까지 갈라줘야 한다.
  const jeonse = jeonseInterest(liabs);
  const norm = buildStdCompare(sp, sp.retire, cn, jeonse.monthly);
  document.getElementById("sp-retire-card").style.display = norm ? "" : "none";
  document.getElementById("sp-bridge-card").style.display = norm ? "" : "none";
  if (norm) {
  const { rows: cmp, totAvg, totRet, byKind, unmapped } = norm;

  // 브릿지(폭포) — 현재 월평균에서 은퇴 월평균까지, 늘어나는 이유를 성격별로 쌓는다.
  renderBridge(totAvg, totRet, byKind, jeonse, norm.moved);

  const cmpMax = Math.max(...cmp.map(x => Math.max(x.avg, x.ret)), 1) * 1.02;
  // 막대는 두 색뿐이다 — 회색=지금, 파랑=은퇴. 예전엔 항목마다 다른 색을 줬는데,
  // 14줄 × 2막대에 15가지 색이 깔리니 정작 읽어야 할 '위아래 길이 차이'가 묻혔다.
  // 항목 색은 왼쪽 점에만 남겨 다른 차트(도넛·스택)와의 연결고리로 쓴다.
  const bar = (v, solid) => `<div class="cmp-line">
    <div class="cmp-fill" style="width:${v / cmpMax * 100}%;background:${solid ? "var(--cmp-ret)" : "var(--cmp-now)"}"></div>
    <span class="cmp-v">${v ? manNum(v) + "만" : "–"}</span></div>`;
  document.getElementById("sp-retire").innerHTML = cmp.map((x, i) => {
    const col = spColor(x.name, i);
    const dm = Math.round((x.ret - x.avg) / 1e4);  // 만원 단위 차이 (미미하면 0 = 무변동)
    const dcls = dm > 0 ? "delta-down" : dm < 0 ? "delta-up" : "delta-none";
    const k = KIND_META[x.kind];
    return `<div class="cmp-row">
      <div class="cmp-name"><span class="chip" style="background:${col}"></span>${esc(x.name)}
        <span class="kind-dot" title="${esc(k.desc)}">${k.icon}</span></div>
      <div class="cmp-track">${bar(x.avg, false)}${bar(x.ret, true)}</div>
      <div class="cmp-diff ${dcls}">${dm ? (dm > 0 ? "+" : "−") + Math.abs(dm) + "만" : "="}</div>
    </div>`;
  }).join("");
  const dTot = totRet - totAvg;
  document.getElementById("sp-retire-head").innerHTML =
    `<span>현재 월평균 <b>${fmtMan(totAvg)}</b></span><span style="color:var(--ink-muted)">→</span>`
    + `<span>은퇴 계획 <b>${fmtMan(totRet)}</b></span>`
    + `<span class="${dTot > 0 ? "delta-down" : "delta-up"}"><b>${dTot > 0 ? "+" : "−"}${fmtMan(Math.abs(dTot))}/월</b></span>`;
  document.getElementById("sp-retire-note").innerHTML =
    "위 막대(연함)=현재 월평균 · 아래 막대(진함)=은퇴 계획. 은퇴가 더 많으면 빨강·적으면 초록.<br>"
    + Object.entries(KIND_META).map(([, m]) => `${m.icon} ${m.label}`).join(" · ")
    + "<br>분류 기준은 <b>가계부(시각화 탭)</b>입니다 — 은퇴 계획이 더 잘게 나눠 둔 항목도 가계부에서 한 칸에 적는 것끼리 접어 비교합니다. "
    + "예: 가계부 <b>생활</b>에는 식비·자기계발·건강이 함께 담기므로 은퇴 계획의 그 항목들도 <b>생활</b>로 합쳤습니다."
    + "<br>양쪽 모두 합계는 전체 금액 그대로입니다(누락 없음). 은퇴 계획은 오늘 가치이며 물가 반영 전 · 참조.연간 생활비 시트 기준."
    + (norm.moved ? `<br>🟡 지금 <b>주거</b>에는 가계부의 주거(관리비)에 더해, 지금 사는 `
        + `오피스텔 보증금을 마련한 대출의 <b>이자 ${manNum(norm.moved)}만/월</b>을 `
        + `<b>대출에서 옮겨</b> 담았습니다 (${(jeonse.parts || []).map(x => `${Math.round(x.amount / 1e8 * 10) / 10}억@${x.rate}%`).join(" + ")}). `
        + `은퇴 계획의 주거비는 월세라, 같은 성격의 돈을 같은 칸에 놓아야 비교가 됩니다. `
        + `더한 게 아니라 옮긴 것이라 합계는 그대로이고, 원금 상환은 저축이라 넣지 않았습니다. `
        + `월별 카테고리 소비·상세 표는 가계부 원본 그대로(대출은 대출)입니다.` : "")
    + (unmapped.length ? `<br><b class="delta-down">⚠️ 표준 분류에 없는 항목 ${unmapped.length}건은 '기타'로 넣었습니다 — ${esc(unmapped.join(", "))}</b>` : "");
  }

  // 표 — 카테고리 × 월 (연 누적 큰 순)
  const rank = [...sp.categories].sort((a, b) =>
    b.values.reduce((s, v) => s + v, 0) - a.values.reduce((s, v) => s + v, 0));
  const cell = v => v ? `<td>${manNum(v)}</td>` : `<td style="color:var(--ink-muted)">·</td>`;
  const body = rank.map(c => {
    const i = sp.categories.indexOf(c);
    return `<tr><td class="name"><span class="chip" style="background:${spColor(c.name, i)}"></span>${c.name}</td>
      ${c.values.map(cell).join("")}
      <td><b>${manNum(c.values.reduce((s, v) => s + v, 0))}</b></td></tr>`;
  }).join("");
  const totRow = `<tr style="border-top:2px solid var(--border)"><td class="name"><b>합계</b></td>
    ${totals.map(v => `<td><b>${manNum(v)}</b></td>`).join("")}
    <td><b>${manNum(ytd)}</b></td></tr>`;
  // 제외 항목(분배)은 버리지 않고 아래에 남겨 원본과 대조할 수 있게 한다
  const exRow = (sp.excluded || []).map(c =>
    `<tr style="color:var(--ink-muted)"><td class="name">${c.name} <small>(제외)</small></td>
      ${c.values.map(v => `<td>${manNum(v)}</td>`).join("")}
      <td>${manNum(c.values.reduce((s, v) => s + v, 0))}</td></tr>`).join("");
  document.getElementById("sp-table").innerHTML =
    `<thead><tr><th>카테고리</th>${months.map(m => `<th>${m.label}</th>`).join("")}<th>누적</th></tr></thead>
     <tbody>${body}${totRow}${exRow}</tbody>`;
  document.getElementById("sp-table").insertAdjacentHTML("afterbegin",
    `<caption style="caption-side:top;text-align:left;font-size:var(--fs-micro);color:var(--ink-muted);padding-bottom:6px">단위: 만원</caption>`);

  // 제외 사유는 항목마다 다르다 — 파이프라인이 붙여 보낸 문구를 그대로 쓴다.
  // 예전엔 "부채 상환이라"로 못박아 둬서, 대출 말고 다른 게 빠지면 각주가 거짓말이 됐다.
  const exNames = (sp.excluded || [])
    .map(c => c.reason ? `${c.name}(${c.reason})` : c.name).join(" · ");
  document.getElementById("sp-note").innerHTML =
    "고정비·변동비 전부 집계"
    + (exNames ? ` · 생활비에서 제외 — ${exNames}. 금액은 표 하단에 그대로 남깁니다.` : "");
}

/* ---- 현금 흐름 계획 (은퇴 후 연 1억을 세금·건보료 없이) ------------------------
   설계 전제는 전부 '사용자가 세운 계획'이다 — 세법 해석을 이 화면이 보증하지 않는다.
   대시보드가 하는 일은 (1) 네 갈래 파이프라인의 계획 대비 진행을 보여주고,
   (2) 실제 데이터로 셀 수 있는 건보료 한도를 감시하고, (3) 언제 무엇을 할지 알려주는 것.

   실측 가능한 건 배당뿐이다. 임대·매도·증여는 미래 행동이라 계획값으로만 둔다.
   핵심: 금융소득 한도는 '과세계좌' 배당만 센다. ISA·연금저축·IRP·퇴직연금은 과세이연이라
   금융소득종합과세 대상이 아니므로, 전체 배당(부부 1,241만)을 그대로 세면 과대계상된다.
   계좌별 tax_rate(0이면 절세계좌)로 데이터에서 직접 갈라낸다. */
const CF_TARGET_YEAR = 2029;
const CF_TARGET = 100000000;      // 부부 합산 연 1억
const CF_DIV_CAP = 9900000;       // 1인 금융소득 통제선 (사용자 설정 990만)

/* 해외주식 기본공제 매도 — 매도'대금'은 상수가 아니라 역산값이다.
   평가액 X를 팔면 차익은 X·(1 − 1/(1+r)) 이고, 거꾸로 X = 차익 ÷ (1 − 1/(1+r)).
   수익률을 보수적으로 10%로 잡는다 (사용자 결정 2026-07-26).

   기준은 '공제 한도'가 아니라 '목표 1억'이다 (사용자 결정) — 목표에서 나머지 3갈래를
   빼고 남는 몫만 판다. 한도를 꽉 채우려면 5,500만까지 팔 수 있지만, 필요 없는 만큼
   더 파는 건 원금을 앞당겨 허무는 일이라 한도를 남기는 쪽이 낫다. */
const CF_GAIN_CAP_EACH = 2500000;                    // 1인 양도차익 기본공제
const CF_GAIN_CAP = CF_GAIN_CAP_EACH * 2;            // 부부 합산 500만
const CF_ASSUMED_RETURN = 0.10;                      // 보수적 수익률 가정
const cfSaleFor = (gain, r) => Math.round(gain / (1 - 1 / (1 + r)));
const cfGainOf = (sale, r) => Math.round(sale * (1 - 1 / (1 + r)));

/* 은퇴 시점의 부동산 세팅 (파이프라인 가정과 같은 전제) — 건보료 재산분의 기준이기도 하다.
   지금 보유한 두 채가 아니라 '계획대로 정리한 뒤'의 모습으로 계산해야 소득분과 기준이 맞는다. */
const CF_OWN_VALUE    = 1500000000;  // 보유 아파트 1채 시세 15억 (임대를 놓는 집)
const CF_OWN_DEPOSIT  = 300000000;   // 세입자에게 받는 보증금 3억 (내 빚이지 재산이 아니다)
const CF_OWN_RENT_M   = 1800000;     // 받는 월세 180만
const CF_LIVE_DEPOSIT = 100000000;   // 우리가 사는 오피스텔 보증금 1억
const CF_LIVE_RENT_M  = 1600000;     // 우리가 내는 월세 160만

const CF_RENT = CF_OWN_RENT_M * 12, CF_GIFT = 28600000, CF_DIV = 19800000;
const CF_BASIC_SALE = CF_TARGET - (CF_RENT + CF_GIFT + CF_DIV);      // 목표에서 역산 = 3,000만
const CF_BASIC_GAIN = cfGainOf(CF_BASIC_SALE, CF_ASSUMED_RETURN);    // 실현 차익 ≈ 273만
const CF_MAX_SALE = cfSaleFor(CF_GAIN_CAP, CF_ASSUMED_RETURN);       // 한도를 다 쓸 때 = 5,500만

const CF_PIPES = [
  { key: "rent",  label: "부동산 임대소득",        plan: CF_RENT, tag: "비과세",
    desc: "월 180만 × 12 · 1세대 1주택 비과세 요건 활용" },
  { key: "basic", label: "해외주식 기본공제 매도",  plan: CF_BASIC_SALE, tag: "비과세",
    desc: `목표 1억에서 나머지 3갈래를 뺀 몫 · 수익률 ${CF_ASSUMED_RETURN * 100}% 가정 시 차익 ${Math.round(CF_BASIC_GAIN / 1e4)}만 (공제 한도의 ${(CF_BASIC_GAIN / CF_GAIN_CAP * 100).toFixed(0)}%)` },
  { key: "gift",  label: "부부 릴레이 증여 후 매도", plan: CF_GIFT, tag: "이월과세 방어",
    desc: "배우자공제 6억/10년 · 증여 후 1년 보유하고 매도" },
  { key: "div",   label: "주식 배당금",            plan: CF_DIV, tag: "건보료 면제",
    desc: "1인 990만 이하로 통제 · 과세계좌 기준" },
];

/* 연중 실행 캘린더. month=0 이면 매월 반복. */
const CF_TASKS = [
  { id: "rent",  pipe: "rent",  month: 0,  day: 25, when: "매월 25일",
    title: "부동산 월세 입금 확인 (180만원)", todo: "파이어 생활비 통장으로 이체" },
  { id: "divq",  pipe: "div",   quarters: [3, 6, 9, 12], day: 28, when: "분기말",
    title: "미국 직상장 ETF(SCHD·VOO·QQQ) 배당 입금 확인",
    todo: "우현·규리 계좌별 수령액 기록 → 990만 한도 게이지 갱신" },
  { id: "gsell", pipe: "gift",  month: 11, day: 15, when: "11월 15일",
    title: "증여받은 주식 매도 실행 (2,860만원)",
    todo: "작년 11월 증여분이 1년 보유를 채웠는지 확인(이월과세 회피) 후 매도·현금화" },
  { id: "bsell", pipe: "basic", month: 12, day: 10, when: "12월 10일",
    title: `해외주식 기본공제 맞춤 매도 (${Math.round(CF_BASIC_SALE / 1e4).toLocaleString()}만원)`,
    todo: `부부 합산 ${Math.round(CF_BASIC_SALE / 1e4).toLocaleString()}만원어치 매도 후 CMA 이체 — 목표 1억을 채우는 몫입니다.`
        + ` 매도 전 실제 평가손익으로 차익을 다시 계산해 1인 ${CF_GAIN_CAP_EACH / 1e4}만(합산 ${CF_GAIN_CAP / 1e4}만) 이내인지 확인할 것`
        + ` · 수익률 ${CF_ASSUMED_RETURN * 100}% 가정 시 차익 ${Math.round(CF_BASIC_GAIN / 1e4)}만으로 한도에 여유가 있습니다` },
  { id: "gift",  pipe: "gift",  month: 12, day: 28, when: "12월 28일",
    title: "내년 인출용 부부간 주식 증여 (2,860만원)",
    todo: "수익률 상위 종목을 배우자 계좌로 대체출고 · 홈택스 증여세 0원 신고" },
];

const cfKey = y => `cf_done_${y}`;
function cfDone(y) { try { return new Set(JSON.parse(localStorage.getItem(cfKey(y)) || "[]")); } catch { return new Set(); } }
function cfToggle(y, id, on) {
  const s = cfDone(y);
  on ? s.add(id) : s.delete(id);
  try { localStorage.setItem(cfKey(y), JSON.stringify([...s])); } catch {}
}

/* 과세계좌(tax_rate>0) 배당만 사람별로 합산 — 건보료 한도의 실측 분모. */
function cfDividends(fin) {
  const out = { 우현: 0, 규리: 0 }, shelter = { 우현: 0, 규리: 0 };
  for (const h of ((fin && fin.holdings) || [])) {
    const o = h.owner;
    if (!(o in out)) continue;
    (h.tax_rate > 0 ? out : shelter)[o] += h.div_krw || 0;
  }
  return { taxable: out, shelter };
}

/* ---- 은퇴 후 지역가입자 건강보험료 (2026년 기준) ----------------------------
   은퇴하면 직장가입자 자격을 잃고 지역가입자가 된다. 지역가입자 보험료는
     건강보험료 = 소득보험료(소득월액 × 7.19%) + 재산보험료(재산점수 × 211.5원)
     장기요양보험료 = 건강보험료 × (0.9448% ÷ 7.19%)
   근거: 국민건강보험법 시행령 별표4 '재산보험료부과점수의 산정방법'(개정 2024.5.7),
         2026년 보험료율 1만분의 719 · 점수당 211.5원 · 최저 20,160원 · 최고 4,591,740원,
         2026년 장기요양보험료율 0.9448%(소득 대비, 보건복지부).
   재산은 '세대' 단위로 합산하고 1억원을 기본공제한다. 금융자산(예금·주식)은 재산에 넣지 않는다. */
const HI = {
  RATE: 0.0719,                  // 지역가입자 소득보험료율 (2026)
  POINT: 211.5,                  // 재산 점수당 금액(원, 2026)
  LTC_OF_INCOME: 0.009448,       // 장기요양보험료율(소득 대비, 2026)
  DEDUCT: 100000000,             // 재산 기본공제 1억원 (2024.2~)
  MIN: 20160, MAX: 4591740,      // 월 건강보험료 하한·상한 (2026)
  PUBLIC: 0.69,                  // 공시가격 ÷ 시세 (공동주택 현실화율 ≈69%) — 가정
  FAIR: 0.60,                    // 재산세 공정시장가액비율 (일반)
  JEONSE: 0.30,                  // 임차 보증금·월세(×40)의 재산 반영률
  FIN_EXEMPT: 10000000,          // 1인 금융소득 연 1,000만원 이하는 건보료 소득에서 제외
};
HI.LTC_MULT = HI.LTC_OF_INCOME / HI.RATE;   // 건강보험료 대비 장기요양 비율 (2026 ≈13.1%)
// 1세대 1주택 재산세 공정시장가액비율 특례 — 공시 3억 이하 43% / 6억 이하 44% / 초과 45%
HI.fairRate = o => o <= 3e8 ? 0.43 : o <= 6e8 ? 0.44 : 0.45;

/* 재산등급별 점수 — [등급 상한(만원), 점수]. 시행령 별표4 전 60등급. */
const HI_TABLE = [
  [450,22],[900,44],[1350,66],[1800,97],[2250,122],[2700,146],[3150,171],[3600,195],
  [4050,219],[4500,244],[5020,268],[5590,294],[6220,320],[6930,344],[7710,365],[8590,386],
  [9570,412],[10700,439],[11900,465],[13300,490],[14800,516],[16400,535],[18300,559],[20400,586],
  [22700,611],[25300,637],[28100,659],[31300,681],[34900,706],[38800,731],[43200,757],[48100,785],
  [53600,812],[59700,841],[66500,881],[74000,921],[82400,961],[91800,1001],[103000,1041],
  [114000,1091],[127000,1141],[142000,1191],[158000,1241],[176000,1291],[196000,1341],
  [218000,1391],[242000,1451],[270000,1511],[300000,1571],[330000,1641],[363000,1711],
  [399300,1781],[439230,1851],[483153,1921],[531468,1991],[584615,2061],[643077,2131],
  [707385,2201],[778124,2271],[Infinity,2341],
];
function hiGrade(won) {
  const man = won / 1e4;
  if (man <= 0) return { grade: 0, points: 0, from: 0, to: 0 };
  for (let i = 0; i < HI_TABLE.length; i++)
    if (man <= HI_TABLE[i][0])
      return { grade: i + 1, points: HI_TABLE[i][1],
               from: i ? HI_TABLE[i - 1][0] * 1e4 : 0, to: HI_TABLE[i][0] * 1e4 };
  return { grade: 60, points: 2341, from: 778124e4, to: Infinity };
}

/* 계획대로 세팅됐을 때의 지역가입자 보험료.
   ⚠️ 재산도 '지금 가진 두 채'가 아니라 은퇴 시점 세팅(15억 1채 보유·임대, 오피스텔 임차)으로 센다 —
      소득분만 은퇴 기준이고 재산분은 현재 자산이면 두 기준이 어긋난다 (2026-07-27 사용자 지적). */
function cfHealthInsurance(taxableDiv) {
  // 보유 주택 — 재산세 과세표준(공시가격 × 공정시장가액비율)이 그대로 건보료 재산이 된다.
  const official = CF_OWN_VALUE * HI.PUBLIC;
  const fair = HI.fairRate(official);                  // 1세대 1주택 특례 (43~45%)
  const props = [{ name: "보유 아파트 (임대)", market: CF_OWN_VALUE, official, base: official * fair, fair }];
  // 임차 오피스텔 — '주택을 소유하지 않은 세대'만 보증금·월세가 재산에 잡힌다(시행령 제42조제1항제2호).
  // 우리는 집을 한 채 갖고 있으므로 이 보증금·월세는 재산에서 빠진다.
  const leases = [{
    name: "거주 오피스텔 (임차)", deposit: CF_LIVE_DEPOSIT, monthly: CF_LIVE_RENT_M,
    would: (CF_LIVE_DEPOSIT + CF_LIVE_RENT_M * 40) * HI.JEONSE,   // 무주택이었다면 잡혔을 금액
    base: 0, why: "주택 보유 세대라 임차 보증금·월세는 재산에서 제외",
  }];
  const propBase = props.reduce((s, p) => s + p.base, 0) + leases.reduce((s, l) => s + l.base, 0);
  const afterDeduct = Math.max(0, propBase - HI.DEDUCT);
  const g = hiGrade(afterDeduct);
  const propPremium = Math.round(g.points * HI.POINT);

  // 소득분 — 계획 4갈래를 건보료 부과 대상인지로 하나씩 판정한다.
  const divEach = Math.max(taxableDiv.우현 || 0, taxableDiv.규리 || 0);
  const incomeItems = [
    { label: "부동산 임대소득", amount: CF_RENT, counted: 0,
      why: "1세대 1주택 비과세 요건 활용 전제 — 비과세 소득은 건보료에도 잡히지 않습니다 (계획 전제)" },
    { label: "해외주식 기본공제 매도", amount: CF_BASIC_SALE, counted: 0,
      why: "양도소득은 지역가입자 소득(이자·배당·사업·근로·연금·기타)에 포함되지 않습니다" },
    { label: "부부 릴레이 증여 후 매도", amount: CF_GIFT, counted: 0,
      why: "증여는 소득이 아니고, 매도분은 양도소득이라 부과 대상이 아닙니다" },
    { label: "주식 배당금", amount: CF_DIV, counted: 0,
      why: `1인 금융소득이 연 ${fmtMan(HI.FIN_EXEMPT)} 이하면 제외 — 계획은 1인 ${fmtMan(CF_DIV_CAP)}로 통제` },
  ];
  const incomeYear = incomeItems.reduce((s, i) => s + i.counted, 0);
  const incPremium = Math.round(incomeYear / 12 * HI.RATE);

  const health = Math.min(HI.MAX, Math.max(HI.MIN, propPremium + incPremium));
  const ltc = Math.round(health * HI.LTC_MULT);
  const monthly = health + ltc;

  // 민감도 — 전제가 깨질 때 얼마나 늘어나는지 (임대 과세 / 배당 한도 초과 / 1주택 특례 종료)
  const withRent = Math.round(CF_RENT / 12 * HI.RATE);
  const rentRisk = Math.round(withRent * (1 + HI.LTC_MULT));
  const divOver = Math.round((CF_DIV_CAP * 2) / 12 * HI.RATE * (1 + HI.LTC_MULT));
  const gGen = hiGrade(Math.max(0, official * HI.FAIR - HI.DEDUCT));   // 특례 없이 60% 적용 시
  const genRisk = Math.round(gGen.points * HI.POINT * (1 + HI.LTC_MULT)) - monthly;

  return { props, leases, propBase, afterDeduct, grade: g, propPremium, fair,
           deposit: CF_OWN_DEPOSIT, incomeItems, incomeYear, incPremium, health, ltc, monthly,
           yearly: monthly * 12, divEach, rentRisk, divOver, genRisk, genGrade: gGen };
}

function renderCashflow(fin, fire) {
  const tabBtn = document.querySelector('.tab[data-tab="cashflow"]');
  if (!fin || !(fin.holdings || []).length) { if (tabBtn) tabBtn.style.display = "none"; return; }
  if (tabBtn) tabBtn.style.display = "";

  const now = new Date(Date.now() + 9 * 3600e3);          // KST
  const year = now.getUTCFullYear(), mon = now.getUTCMonth() + 1, day = now.getUTCDate();
  const { taxable, shelter } = cfDividends(fin);
  const divActual = taxable.우현 + taxable.규리;

  // ── Section 1: 요약 KPI ────────────────────────────────────────────────
  const planned = CF_PIPES.reduce((s, p) => s + p.plan, 0);
  const hi = cfHealthInsurance(taxable);
  document.getElementById("cf-kpis").innerHTML =
    kpiCard(`${CF_TARGET_YEAR}년 목표 현금흐름`, fmtMan(CF_TARGET),
            `설계 합계 ${fmtMan(planned)} · 목표 대비 ${(planned / CF_TARGET * 100).toFixed(0)}%`, true) +
    kpiCard("올해 실측 배당 (과세계좌)", fmtMan(divActual),
            `한도 ${fmtMan(CF_DIV_CAP * 2)} 대비 ${(divActual / (CF_DIV_CAP * 2) * 100).toFixed(0)}% · 우현 ${manNum(taxable.우현)}만 / 규리 ${manNum(taxable.규리)}만`) +
    kpiCard("계획대로일 때 예상 건보료", fmtWon(hi.monthly) + "/월",
            `연 ${fmtMan(hi.yearly)} · 재산분 ${manNum(hi.propPremium)}만 + 소득분 ${manNum(hi.incPremium)}만 · 장기요양 포함`);

  // ── Section 1-b: 파이프라인 ───────────────────────────────────────────
  //   실측이 있는 항목(배당)은 진하게 채우고, 미래 행동(임대·매도·증여)은 계획값만 흐리게.
  const maxPlan = Math.max(...CF_PIPES.map(p => p.plan));
  const COL = { rent: "var(--c-re)", basic: "var(--c-us)", gift: "var(--c-vi)", div: "var(--c-kr)" };
  document.getElementById("cf-pipes").innerHTML = CF_PIPES.map(p => {
    const actual = p.key === "div" ? divActual : null;
    const w = (actual != null ? actual : p.plan) / maxPlan * 100;
    const pct = actual != null ? actual / p.plan * 100 : null;
    return `<div class="cf-pipe">
      <div class="cf-pipe-name">${esc(p.label)} <span class="cf-tag">${esc(p.tag)}</span>
        <small>${esc(p.desc)}</small></div>
      <div class="cf-pipe-track">
        <div class="cf-pipe-fill" style="width:${w}%;background:${COL[p.key]};opacity:${actual != null ? 1 : .42}"></div>
      </div>
      <div class="cf-pipe-v">${actual != null
        ? `<b>${fmtMan(actual)}</b><br><span style="color:var(--ink-muted)">계획 ${fmtMan(p.plan)} · ${pct.toFixed(0)}%</span>`
        : `<b>${fmtMan(p.plan)}</b><br><span style="color:var(--ink-muted)">계획</span>`}</div>
    </div>`;
  }).join("");
  document.getElementById("cf-pipes-note").innerHTML =
    "진한 막대 = 실제 데이터로 확인된 금액 · 흐린 막대 = 아직 실행 전인 계획값. "
    + "임대·매도·증여는 미래 행동이라 계획값으로만 둡니다.<br>"
    + `<b>기본공제 매도 ${fmtMan(CF_BASIC_SALE)}</b>은 목표 1억에서 나머지 3갈래(${fmtMan(CF_RENT + CF_GIFT + CF_DIV)})를 뺀 몫입니다. `
    + `수익률 ${CF_ASSUMED_RETURN * 100}% 가정이면 실현 차익은 <b>${fmtMan(CF_BASIC_GAIN)}</b>으로 공제 한도 ${fmtMan(CF_GAIN_CAP)}의 `
    + `${(CF_BASIC_GAIN / CF_GAIN_CAP * 100).toFixed(0)}%만 씁니다.<br>`
    + `한도를 꽉 채우려면 ${fmtMan(CF_MAX_SALE)}까지 팔 수 있지만 그러면 목표를 ${fmtMan(CF_MAX_SALE - CF_BASIC_SALE)} 넘깁니다 — `
    + `필요 없는 만큼 더 파는 건 원금을 앞당겨 허무는 일이라, <b>한도 여유 ${fmtMan(CF_GAIN_CAP - CF_BASIC_GAIN)}은 남겨 두는 쪽</b>을 택했습니다. `
    + `수익률이 예상보다 높게 나오면 같은 3,000만 매도로도 차익이 커지니, 그때 한도 여유가 완충이 됩니다.<br>`
    + "⚠️ 비과세 요건·공제 한도는 <b>우현님이 세운 계획 전제</b>이며 이 화면이 세법 해석을 보증하지 않습니다. 실제 신고 전 세무 전문가 확인을 권합니다.";

  // ── Section 1-c: 예상 건강보험료 ──────────────────────────────────────
  //   계획 4갈래가 각각 건보료 부과 대상인지 판정하고, 재산분은 시행령 등급표로 실제 계산한다.
  // 항목명과 설명을 한 셀에 쌓는다 — 3열로 두면 좁은 패널에서 이름 열이 눌려 세로로 쪼개진다.
  const hiRow = (a, b, c, cls = "") => `<tr class="${cls}">
    <td><div class="hi-name">${a}</div>${c ? `<div class="hi-why">${c}</div>` : ""}</td>
    <td class="num">${b}</td></tr>`;
  const eok = v => (v / 1e8).toFixed(2) + "억";
  document.getElementById("cf-hi").innerHTML = `
    <div class="hi-head">
      <div class="hi-big">${fmtWon(hi.monthly)}<small>/월</small></div>
      <div class="hi-sub">연 ${fmtMan(hi.yearly)} · 건강보험료 ${fmtWon(hi.health)} + 장기요양 ${fmtWon(hi.ltc)}</div>
    </div>
    <div class="hi-grid">
      <div class="hi-panel">
        <div class="hi-h">① 소득분 — <b>${fmtWon(hi.incPremium)}</b></div>
        <table class="hi-tbl"><tbody>
          ${hi.incomeItems.map(i => hiRow(esc(i.label),
              `${fmtMan(i.amount)} → <b class="cf-lv-ok">0원</b>`, esc(i.why))).join("")}
          ${hiRow("<b>건보료 부과 소득</b>", `<b>${fmtMan(hi.incomeYear)}</b>`,
                  "목표 1억 중 부과 대상은 0원 — 양도·증여는 대상 밖, 배당은 1인 한도 이하", "hi-tot")}
        </tbody></table>
      </div>
      <div class="hi-panel">
        <div class="hi-h">② 재산분 — <b>${fmtWon(hi.propPremium)}</b></div>
        <table class="hi-tbl"><tbody>
          ${hi.props.map(p => hiRow(esc(p.name),
              eok(p.base), `시세 ${eok(p.market)} × 공시 ${(HI.PUBLIC*100).toFixed(0)}% = ${eok(p.official)}`
                         + ` × 과표 ${(p.fair*100).toFixed(0)}% (1세대 1주택 특례)`)).join("")}
          ${hi.leases.map(l => hiRow(esc(l.name),
              `<span style="color:var(--ink-muted)">0</span>`,
              `보증금 ${eok(l.deposit)} · 월세 ${manNum(l.monthly)}만 — ${esc(l.why)}`
              + `<br>무주택이었다면 ${eok(l.would)}이 잡혔을 자리입니다`)).join("")}
          ${hiRow("받는 임대보증금", `<span style="color:var(--ink-muted)">0</span>`,
                  `${eok(hi.deposit)}은 세입자에게 돌려줄 빚이라 재산이 아닙니다 (부채도 차감되지 않음)`)}
          ${hiRow("기본공제", `−${eok(HI.DEDUCT)}`, "세대당 1억원 (2024.2~)")}
          ${hiRow("<b>재산금액</b>", `<b>${eok(hi.afterDeduct)}</b>`,
                  `${hi.grade.grade}등급 · ${hi.grade.points.toLocaleString()}점 × ${HI.POINT}원`, "hi-tot")}
        </tbody></table>
      </div>
    </div>`;
  document.getElementById("cf-hi-note").innerHTML =
    `<b>기준</b> — 지금 가진 두 채가 아니라 <b>계획대로 정리한 뒤</b>의 모습(시세 ${eok(CF_OWN_VALUE)} 아파트 1채 보유·임대, `
    + `보증금 ${eok(CF_OWN_DEPOSIT)}/월세 ${manNum(CF_OWN_RENT_M)}만, 우리는 보증금 ${eok(CF_LIVE_DEPOSIT)}/월세 ${manNum(CF_LIVE_RENT_M)}만 오피스텔 거주)으로 계산했습니다. `
    + `소득분만 은퇴 기준이고 재산분은 현재 자산이면 두 기준이 어긋나기 때문입니다.<br>`
    + `<b>왜 이렇게 낮은가</b> — 목표 현금흐름 1억은 대부분 <b>건보료 부과 대상이 아닌 돈</b>입니다. `
    + `양도소득(매도·증여 후 매도)은 지역가입자 소득에 아예 포함되지 않고, 배당은 1인 ${fmtMan(HI.FIN_EXEMPT)} 이하로 `
    + `묶어 두면 제외됩니다. 그래서 사실상 <b>재산분만</b> 남고, 금융자산(예금·주식)은 재산에 넣지 않으므로 `
    + `건보료를 좌우하는 건 <b>보유한 집 한 채</b>뿐입니다. 우리가 사는 오피스텔 보증금·월세는 `
    + `<b>주택을 소유한 세대라 재산에서 빠집니다</b>(무주택 세대만 임차 보증금이 재산에 잡힙니다).<br>`
    + `⚠️ <b>전제가 깨지면</b> — 임대소득이 과세로 잡히면 <b>+${fmtWon(hi.rentRisk)}/월</b>, `
    + `배당이 1인 ${fmtMan(HI.FIN_EXEMPT)}을 넘기면 그 사람 배당 전액이 소득에 산입돼 최대 <b>+${fmtWon(hi.divOver)}/월</b>, `
    + `1세대 1주택 공정시장가액비율 특례가 사라져 ${(HI.FAIR*100).toFixed(0)}%로 돌아가면 <b>+${fmtWon(hi.genRisk)}/월</b>(${hi.genGrade.grade}등급)까지 늘 수 있습니다.<br>`
    + `📐 <b>계산 근거</b> — 국민건강보험법 시행령 별표4(재산보험료부과점수, 60등급) · 2026년 보험료율 ${(HI.RATE*100).toFixed(2)}% · `
    + `점수당 ${HI.POINT}원 · 장기요양 ${(HI.LTC_OF_INCOME*100).toFixed(4)}%(건보료의 ${(HI.LTC_MULT*100).toFixed(1)}%) · `
    + `재산 기본공제 1억원 · 최저 ${fmtWon(HI.MIN)}·최고 ${fmtWon(HI.MAX)}. 재산은 세대 합산이며 부채는 차감되지 않습니다.<br>`
    + `공시가격은 시세의 ${(HI.PUBLIC*100).toFixed(0)}%(공동주택 현실화율), 재산세 공정시장가액비율은 1세대 1주택 특례 ${(hi.fair*100).toFixed(0)}%로 가정했습니다 — `
    + `실제 공시가격이 나오면 값이 달라집니다. 참고용이며 확정 고지액이 아닙니다.`;

  // ── Section 2: 지향하는 자산 구성 (은퇴 시점) ─────────────────────────
  //   계획대로 정리했을 때 순자산이 어떤 모양이어야 하는지 — 부동산 15억 1채를 고정으로 두면
  //   나머지가 곧 금융자산이다. 지금 금융자산에서 얼마를 더 쌓아야 하는지가 바로 읽힌다.
  const nowFin = (fin.holdings || []).reduce((s, h) => s + h.value_krw, 0);
  const tRow = document.getElementById("cf-target");
  tRow.innerHTML = "";
  const reNet = CF_OWN_VALUE - CF_OWN_DEPOSIT;         // 부동산 순지분 (보증금은 돌려줄 돈)
  const targetDonut = (title, caption, net) => {
    const finAsset = Math.max(0, net - reNet - CF_LIVE_DEPOSIT);
    donut(donutCell(tRow), {
      title, caption, center: net, centerLabel: "순자산", fmt: fmtEok, legendValue: true,
      annotateTop: 3, annFmt: v => (v / 1e8).toFixed(1) + "억",
      slices: [
        { label: "부동산 순지분", value: reNet, color: "var(--c-re)" },
        { label: "금융자산", value: finAsset, color: "var(--c-us)" },
        { label: "거주 보증금", value: CF_LIVE_DEPOSIT, color: "var(--c-kr)" },
      ].filter(s => s.value > 0),
    });
    return finAsset;
  };
  const projected = (fire && fire.retire_asset) || 0;
  const goal = (fire && fire.target_basic) || 0;
  const needProj = projected ? targetDonut("예상대로 갔을 때", `${(fire.target_year)||""}년 예상 순자산`, projected) : 0;
  const needGoal = goal ? targetDonut("FIRE 기본 목표를 채우면", "기대수명까지 소진 기준", goal) : 0;
  document.getElementById("cf-target-note").innerHTML =
    `<b>읽는 법</b> — 은퇴 시점 부동산을 <b>시세 ${eok(CF_OWN_VALUE)} 한 채</b>로 고정하면, 순자산에서 `
    + `부동산 순지분(${eok(reNet)} = ${eok(CF_OWN_VALUE)} − 임대보증금 ${eok(CF_OWN_DEPOSIT)})과 거주 보증금 ${eok(CF_LIVE_DEPOSIT)}을 뺀 나머지가 `
    + `곧 <b>금융자산</b>입니다. 이 금융자산이 파이프라인 네 갈래(배당·매도·증여)를 돌리는 원천입니다.<br>`
    + (projected ? `예상대로면 금융자산 <b>${eok(needProj)}</b> — 지금 ${eok(nowFin)}에서 <b>${eok(Math.max(0, needProj - nowFin))}</b>을 더 쌓아야 합니다. ` : "")
    + (goal ? `FIRE 기본 목표(${eok(goal)})를 채우면 금융자산은 <b>${eok(needGoal)}</b>이 됩니다.` : "")
    + `<br>부동산 비중이 커 보이는 건 <b>집이 현금을 만들지 못하기 때문</b>입니다 — 목표 현금흐름 1억 중 임대는 ${fmtMan(CF_RENT)}뿐이고, `
    + `나머지 ${fmtMan(CF_TARGET - CF_RENT)}은 금융자산에서 나옵니다. 그래서 은퇴가 가까울수록 금융자산 쪽을 키우는 게 계획의 핵심입니다.`;

  // ── Section 3: 실행 캘린더 ────────────────────────────────────────────
  const done = cfDone(year);
  const nextOf = t => {                     // 오늘 기준 며칠 뒤인지 (가까운 것 강조용)
    if (t.month === 0) {                    // 매월 반복 — 이번 달이 지났으면 다음 달 같은 날
      if (day <= t.day) return t.day - day;
      const eom = new Date(Date.UTC(year, mon, 0)).getUTCDate();
      return (eom - day) + t.day;
    }
    let best = 9999;
    for (const m of (t.quarters || [t.month])) {
      const d = Math.round((Date.UTC(year, m - 1, t.day) - Date.UTC(year, mon - 1, day)) / 864e5);
      if (d >= 0) best = Math.min(best, d);
    }
    return best;
  };
  const withD = CF_TASKS.map(t => ({ t, d: nextOf(t) }));
  const soonest = Math.min(...withD.map(x => x.d));
  const taskId = t => t.month === 0 ? `${t.id}-${year}-${String(mon).padStart(2, "0")}`
    : t.quarters ? `${t.id}-${year}-Q${Math.ceil(mon / 3)}` : `${t.id}-${year}`;
  document.getElementById("cf-cal").innerHTML = withD.map(({ t, d }) => {
    const id = taskId(t), isDone = done.has(id);
    return `<div class="cf-task${d === soonest ? " next" : ""}${isDone ? " done" : ""}" data-id="${esc(id)}">
      <input type="checkbox" class="cf-chk" ${isDone ? "checked" : ""} aria-label="완료">
      <div class="cf-when">${esc(t.when)}${d === soonest ? `<span class="cf-next-badge">다음</span>` : ""}</div>
      <div>
        <div class="cf-title">${esc(t.title)}</div>
        <div class="cf-todo">${esc(t.todo)}</div>
      </div>
    </div>`;
  }).join("");
  document.getElementById("cf-cal").onchange = ev => {
    const box = ev.target.closest(".cf-chk"); if (!box) return;
    const row = box.closest(".cf-task");
    cfToggle(year, row.dataset.id, box.checked);
    row.classList.toggle("done", box.checked);
  };
  document.getElementById("cf-cal-note").textContent =
    `체크는 이 브라우저에만 저장됩니다(${year}년 기준) · 매월·분기 항목은 달이 바뀌면 새로 체크할 수 있습니다.`;

}

