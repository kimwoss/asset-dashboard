/* ---- 히어로 밴드 (탭 위 고정) ----
   '지금 순자산 + 오늘 변화 + FIRE 진척' 세 가지만. 여기서 더 늘리면 요약이 아니라
   또 하나의 표가 된다. 전일은 칩으로 승격하고 전월·전년은 보조행으로 내린다 —
   종전엔 셋이 같은 크기라 '오늘 어땠나'가 묻혔다. */
function renderHeroBand(snap, net) {
  const el = document.getElementById("heroband");
  if (!el || !net) return;
  el.className = "heroband";
  el.style.display = "";

  const d = snap.prev_day && snap.prev_day.net_krw ? net - snap.prev_day.net_krw : null;
  const chip = d == null ? ""
    : `<span class="delta-chip ${d >= 0 ? "up" : "dn"}">${d >= 0 ? "▲" : "▼"} ${eokMan(Math.abs(d))}</span>`;

  const subs = [["전월", snap.prev_month], ["전년", snap.prev_year]].map(([lb, b]) => {
    const base = b && b.net_krw;
    if (!base) return "";
    const p = (net - base) / base * 100;
    return `<span>${lb} <b style="color:${p >= 0 ? "var(--pos)" : "var(--neg)"}">`
         + `${p >= 0 ? "+" : ""}${p.toFixed(1)}%</b></span>`;
  }).filter(Boolean).join("");

  const f = snap.fire || {};
  const gauge = (lb, target, color) => {
    if (!target) return "";
    const p = net / target * 100;
    return `<div>
      <div class="hb-g-head"><span>${lb}</span><b>${p.toFixed(1)}%</b></div>
      <div class="hb-track"><div class="hb-fill" style="width:${Math.min(100, p).toFixed(1)}%;background:${color}"></div></div>
    </div>`;
  };
  const gauges = gauge("FIRE 기본", f.target_basic, "var(--c-us)")
               + gauge("FIRE 부자", f.target_rich, "var(--c-vi)");

  el.innerHTML = `
    <div class="hb-main">
      <span class="u-label">순자산</span>
      <div class="hb-val">${eokMan(net)}</div>
      <div class="hb-deltas">${chip}${subs ? `<span class="hb-sub">${subs}</span>` : ""}</div>
    </div>
    ${gauges ? `<div class="hb-gauges">${gauges}</div>` : ""}`;
}

function kpiCard(label, value, sub, hero) {
  return `<div class="card${hero ? " hero" : ""}">
    <div class="label">${label}</div><div class="value">${value}</div>
    ${sub ? `<div class="sub">${sub}</div>` : ""}</div>`;
}

/* ---- FIRE 목표 달성 (★종합 시트 목표 + 실시간 순자산 달성률) ---- */
function renderFire(f, net) {
  const sec = document.getElementById("fire-section");
  if (!f || !f.target_basic) { sec.style.display = "none"; return; }
  sec.style.display = "";

  const goal = (label, note, target, color) => {
    const pct = target > 0 ? net / target * 100 : 0;
    const remain = target - net;
    return `<div>
      <div class="goal-head">
        <span class="gl">${label} <small>· ${note} · 목표 ${fmtEok(target)}</small></span>
        <span class="pct" style="color:${color}">${pct.toFixed(1)}%</span>
      </div>
      <div class="goal-track"><div class="goal-fill" style="width:${Math.min(100, pct).toFixed(1)}%;background:${color}"></div></div>
      <div class="goal-sub">${remain > 0 ? "남은 목표 " + fmtEok(remain) : "목표 달성 (+" + fmtEok(-remain) + ")"}</div>
    </div>`;
  };

  let html = `<div class="fire-goals">
    ${goal("기본 루트", "기대수명까지 소진", f.target_basic, "var(--c-us)")}
    ${goal("부자 루트", "자산 유지·증식", f.target_rich, "var(--c-vi)")}
  </div>`;

  // ★종합의 나이는 전부 우현 기준 한 사람 것이다. 규리는 age_gap살 아래(시트에 없어
  // sheets_fire가 넘겨준다) — 나이가 나오는 자리마다 두 사람을 함께 적는다.
  const dual = a => (f.age_gap && a) ? `${f.age_self} ${a} · ${f.age_spouse} ${a - f.age_gap}세` : `${a}세`;

  const facts = [];
  if (f.target_year) {
    // 목표 시점은 '연도+월'(예: 2028년 4월)의 1일. 예전엔 12월 31일로 잡아 8개월 늦게 셌다.
    const tm = f.target_month || 12;
    const dday = Math.round((new Date(f.target_year, tm - 1, 1) - new Date()) / 864e5);
    const when = dday > 0 ? `D-${dday} · ${Math.floor(dday / 365)}년 ${Math.floor(dday % 365 / 30)}개월` : "목표 시점 도래";
    facts.push(["은퇴 목표", f.retire_age ? dual(f.retire_age) : `${f.target_year}년 ${tm}월`,
                `${f.target_year}년 ${tm}월 · ${when}`, !!f.retire_age]);
  }
  if (f.monthly_expense) facts.push(["은퇴 후 월생활비", fmtWon(f.monthly_expense), "물가 반영"]);
  if (f.depletion_age) facts.push(["자산 소진 예상", dual(f.depletion_age),
                                   f.life_expectancy ? `기대수명 각 ${f.life_expectancy}세` : "", true]);
  if (f.real_return) facts.push(["세후 실질수익률", `${f.real_return}%`, "연 가정치"]);
  if (f.current_age) facts.push(["현재 나이", dual(f.current_age), `${f.current_year || ""}년 기준`, true]);
  if (facts.length)
    html += `<div class="fire-facts">${facts.map(([l, v, s, isDual]) =>
      `<div class="fact"><div class="l">${l}</div><div class="v${isDual ? " dual" : ""}">${v}</div>${s ? `<div class="s">${s}</div>` : ""}</div>`).join("")}</div>`;

  document.getElementById("fire-body").innerHTML = html;
}

/* ---- 금융자산 탭 (★주식계좌 원 소스) ---- */
const TCOL = {
  "KRX:360750": "#3182F6", "KRX:379810": "#7048E8", "KRX:435420": "#0CA678",
  "KRX:458730": "#F59F00", "KRX:148020": "#E64980", "KRX:161510": "#37B24D",
  "SCHD": "#1098AD",
};
const colorOf = t => TCOL[t] || "var(--baseline)";
const fmtMan = v => Math.round(v / 1e4).toLocaleString("ko-KR") + "만원";

/* 추종 지수별 분류 — 국내 상장 ETF도 실제로 추종하는 지수로 묶는다.
   TIGER 미국배당다우존스는 SCHD와 같은 지수(Dow Jones US Dividend 100)라 합쳐야
   실제 노출이 드러난다. 채권혼합50은 이름대로 나스닥100 50% + 채권 50%로 쪼갠다.
   split: [[카테고리, 비중], ...] — 합이 1 */
const IDX_GROUP = {
  "SCHD":       [["미국 배당다우존스", 1]],
  "KRX:458730": [["미국 배당다우존스", 1]],   // TIGER 미국배당다우존스 = 한국판 SCHD
  "KRX:360750": [["S&P500", 1]],
  "KRX:379810": [["나스닥100", 1]],
  "KRX:435420": [["나스닥100", 0.5], ["채권", 0.5]],  // TIGER 미국나스닥100채권혼합50
  "KRX:148020": [["국내 KOSPI200", 1]],
  "KRX:161510": [["국내 고배당", 1]],
};
const IDX_COLOR = {
  "미국 배당다우존스": "#1098AD", "나스닥100": "#7048E8", "S&P500": "#3182F6",
  "국내 KOSPI200": "#E64980", "국내 고배당": "#37B24D",
  "채권": "#0CA678", "현금": "var(--baseline)",
};

function byIndex(hs) {
  const m = new Map();
  for (const h of hs) {
    if (!(h.value_krw > 0)) continue;
    // 티커 없는 행(청약·CMA 예치금 등)은 현금
    for (const [cat, w] of IDX_GROUP[h.ticker] || [["현금", 1]])
      m.set(cat, (m.get(cat) || 0) + h.value_krw * w);
  }
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
}

function indexDonut(cell, title, hs) {
  const total = sum(hs);
  if (total <= 0) {
    cell.innerHTML = `<h3>${title}</h3><div class="cap">보유내역 입력 전</div>
      <div style="height:150px;display:flex;align-items:center;color:var(--ink-muted);font-size:var(--fs-cap)">—</div>`;
    return;
  }
  // 종목별 도넛과 한 카드에서 토글로 갈아끼우므로 가운데 총액을 같이 보여준다
  // (동시에 보이지 않아 중복이 아니고, 없으면 모드를 바꿀 때 숫자만 사라져 어색하다).
  donut(cell, {
    title, caption: "추종 지수별", center: total, centerLabel: "금융자산",
    slices: byIndex(hs).map(([cat, v]) => ({
      label: cat, value: v, color: IDX_COLOR[cat] || "var(--baseline)" })),
  });
}

function byName(hs) {
  const m = new Map();
  for (const h of hs) {
    if (!(h.value_krw > 0)) continue;
    const k = h.name || h.account;
    const cur = m.get(k) || { value: 0, ticker: h.ticker };
    cur.value += h.value_krw;
    m.set(k, cur);
  }
  return [...m.entries()].sort((a, b) => b[1].value - a[1].value);
}
const sum = (hs, f = h => h.value_krw) => hs.reduce((s, h) => s + f(h), 0);

function portfolioDonut(cell, title, hs) {
  const total = sum(hs);
  if (total <= 0) {
    cell.innerHTML = `<h3>${title}</h3><div class="cap">보유내역 입력 전</div>
      <div style="height:150px;display:flex;align-items:center;color:var(--ink-muted);font-size:var(--fs-cap)">—</div>`;
    return;
  }
  donut(cell, {
    title, caption: "종목별 평가액", center: total, centerLabel: "금융자산",
    slices: byName(hs).map(([name, o]) => ({ label: name, value: o.value, color: colorOf(o.ticker) })),
  });
}

function stackBar(label, pension, liquid) {
  const tot = pension + liquid;
  if (tot <= 0) return "";
  const pp = pension / tot * 100, lp = liquid / tot * 100;
  return `<div class="sb">
    <div class="sb-head"><b>${label}</b><span style="color:var(--ink-muted)">${fmtEok(tot)}</span></div>
    <div class="sb-track">
      ${pension > 0 ? `<div class="sb-seg" style="width:${pp}%;background:var(--c-vi)">${pp >= 10 ? pp.toFixed(0) + "%" : ""}</div>` : ""}
      ${liquid > 0 ? `<div class="sb-seg" style="width:${lp}%;background:var(--c-us)">${lp >= 10 ? lp.toFixed(0) + "%" : ""}</div>` : ""}
    </div>
    <div class="goal-sub">연금성 ${fmtEok(pension)} · 유동성 ${fmtEok(liquid)}</div>
  </div>`;
}

