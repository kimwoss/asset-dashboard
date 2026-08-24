/* ---- 히어로 밴드 (탭 위 고정) ----
   '지금 순자산 + 오늘 변화 + FIRE 진척' 세 가지만. 여기서 더 늘리면 요약이 아니라
   또 하나의 표가 된다. 전일은 칩으로 승격하고 전월·전년은 보조행으로 내린다 —
   종전엔 셋이 같은 크기라 '오늘 어땠나'가 묻혔다. */
// 접힘 상태는 localStorage에 남긴다. 회사에서 열 때 매번 다시 접어야 한다면
// 가리개 구실을 못 한다 — 한 번 접으면 다음에도 접힌 채로 열린다.
const HB_HIDE_KEY = "hb_hidden";
const hbHidden = () => localStorage.getItem(HB_HIDE_KEY) === "1";

/* ── 표지 미디어 ────────────────────────────────────────────────────────────
   제네시스처럼 사진·영상이 서서히 교차되며 바뀐다. 소재를 여기에만 적어 두면
   나머지는 알아서 돈다 — 1장이면 교차 없이 켄번스만, 2장 이상이면 순환.

   사진 추가하는 법: docs/assets/에 파일을 넣고 아래 배열에 한 줄 더한다.
     · lg/md/sm 세 크기를 넣으면 화면 폭에 맞는 것만 받는다(없으면 lg 하나로도 된다)
     · 영상은 {video: "assets/xxx.mp4", poster: "assets/xxx.jpg"} 로
   ⚠️ 전부 미리 받지 않는다. 지금 것과 '다음 것' 하나만 받아 둔다 — 표지 하나 보려고
      매번 몇 MB를 받게 하면 아침에 폰으로 여는 그 몇 초가 그대로 손해다. */
const COVER_MEDIA = [
  // 배치는 하루의 흐름 — 낮 → 해질녘 → 밤. 넓은 컷과 가까운 컷을 번갈아 리듬을 준다.
  // 2022년 5월 포르투갈 19컷. 사진의 EXIF 촬영 시각으로 시간대를 갈랐다(추측이 아니다).
  // fit:true = 세로 사진. 가로 띠에 꽉 채우면 인물만 크게 잘리므로 사진 전체를 담고
  //            남는 좌우는 같은 사진을 흐리게 깔아 메운다(얼굴이 작아지고 배경이 산다).
  // focus는 가로 사진을 띠에 맞춰 자를 때 어디를 남길지.
  // video는 아이폰 라이브 포토를 3배 늦추고 정방향→역방향으로 이어 붙인 것 —
  //            1초짜리를 그대로 돌리면 9초 동안 열 번 튄다.

  // ── 낮 ──────────────────────────────────────────────────────────────────
  { slug: "porto-bridge",      focus: "center 42%", caption: "Porto · Dom Luís I" },
  { slug: "lisboa-chiado",     focus: "center 46%", caption: "Lisboa · Chiado" },
  { slug: "porto-douro-wide",  focus: "center 55%", caption: "Porto · Vila Nova de Gaia" },
  { slug: "lisboa-arch",       focus: "center 55%", caption: "Lisboa · Baixa" },
  { slug: "hero",              focus: "center 58%", caption: "Porto · Douro 2022" },
  { slug: "chiado-brasileira", caption: "Lisboa · A Brasileira",
    video: "assets/chiado-brasileira.mp4", poster: "assets/chiado-brasileira-poster.jpg" },
  { slug: "douro-window",      fit: true,           caption: "Porto · Douro" },
  { slug: "belem-tower",       focus: "center 45%", caption: "Lisboa · Torre de Belém" },
  { slug: "pastel-nata",       fit: true,           caption: "Porto · Pastel de Nata" },
  { slug: "porto-bridge-view", focus: "center 50%", caption: "Porto · Ponte Dom Luís I" },
  { slug: "lisboa-table",      caption: "Lisboa · 그날의 점심",
    video: "assets/lisboa-table.mp4", poster: "assets/lisboa-table-poster.jpg" },

  // ── 해질녘 ──────────────────────────────────────────────────────────────
  { slug: "ribeira-street",    focus: "center 52%", caption: "Porto · Ribeira" },
  { slug: "douro-terrace",     focus: "center 50%", caption: "Porto · Cais da Ribeira" },
  { slug: "azenhas-do-mar",    focus: "center 45%", caption: "Sintra · Azenhas do Mar" },
  { slug: "porto-miradouro",   focus: "center 55%", caption: "Porto · Miradouro" },
  { slug: "sintra-wine",       fit: true,           caption: "Sintra · 2022" },

  // ── 밤 ──────────────────────────────────────────────────────────────────
  { slug: "lisboa-wine",       focus: "center 50%", caption: "Sintra · Vinho" },
  { slug: "alfama-night",      focus: "center 45%", caption: "Lisboa · Alfama" },
  { slug: "porto-night",       focus: "center 46%", caption: "Porto · Ribeira Night" },
].map(m => ({ ...m,
  lg: `assets/${m.slug}.webp`, md: `assets/${m.slug}-md.webp`,
  sm: `assets/${m.slug}-sm.webp`, fallback: `assets/${m.slug}.jpg` }));
const COVER_HOLD_MS = 9000;     // 한 장이 머무는 시간

function coverSrc(m) {
  const w = window.innerWidth;
  const pick = w <= 760 ? (m.sm || m.md || m.lg) : w <= 1400 ? (m.md || m.lg) : m.lg;
  return pick || m.fallback;
}

function startCover() {
  const stack = document.getElementById("cover-stack");
  const capEl = document.getElementById("cover-cap");
  const cover = document.getElementById("cover");
  if (!stack || !cover || !COVER_MEDIA.length) return;
  cover.hidden = false;

  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const layers = [document.createElement("div"), document.createElement("div")];
  for (const l of layers) {
    l.className = "cover-layer";
    l.innerHTML = '<div class="cl-blur"></div><div class="cl-main"></div>';
    stack.appendChild(l);
  }

  let idx = 0, front = 0;
  const paint = (layer, m) => {
    const main = layer.querySelector(".cl-main"), blur = layer.querySelector(".cl-blur");
    if (m.video) {
      main.innerHTML = `<video muted playsinline loop autoplay preload="none"
        poster="${m.poster || ""}"><source src="${m.video}"></video>`;
      return;
    }
    const url = `url("${coverSrc(m)}")`;
    main.style.backgroundImage = url;
    main.style.backgroundPosition = m.fit ? "center" : (m.focus || "center 58%");
    layer.classList.toggle("fit", !!m.fit);
    blur.style.backgroundImage = m.fit ? url : "none";
  };
  const show = i => {
    const m = COVER_MEDIA[i];
    const next = layers[front ^ 1];
    paint(next, m);
    // 켄번스는 매번 새로 시작해야 한다 — 클래스를 뗐다 붙여 애니메이션을 되감는다
    next.classList.remove("kb"); void next.querySelector(".cl-main").offsetWidth;
    if (!still) next.classList.add("kb");
    next.classList.add("on");
    layers[front].classList.remove("on");
    front ^= 1;
    if (capEl) capEl.textContent = m.caption || "";
  };

  show(0);
  if (COVER_MEDIA.length < 2 || still) return;   // 한 장뿐이면 순환할 것이 없다

  const preload = i => {                          // 다음 것만 미리 (전부 받지 않는다)
    const m = COVER_MEDIA[i];
    if (m.video) return;
    const img = new Image(); img.src = coverSrc(m);
  };
  preload(1);
  setInterval(() => {
    idx = (idx + 1) % COVER_MEDIA.length;
    show(idx);
    preload((idx + 1) % COVER_MEDIA.length);
  }, COVER_HOLD_MS);
}

function renderHeroBand(snap, net) {
  const el = document.getElementById("heroband");
  if (!el || !net) return;
  el.className = "heroband" + (hbHidden() ? " hb-off" : "");
  el.style.display = "";
  if (!startCover._done) { startCover._done = true; startCover(); }

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
    ${gauges ? `<div class="hb-gauges">${gauges}</div>` : ""}
    <button class="hb-toggle" type="button" aria-expanded="${!hbHidden()}"
            aria-controls="heroband" title="순자산 카드 접기/펴기">
      <span class="hb-eye"></span><span class="hb-lb"></span></button>`;
  syncHeroBand(el);
}

/* 접힘 상태를 화면에 반영. 값 자체를 지우지 않고 가리기만 한다 —
   다시 펼 때 새로 그릴 필요가 없고, 접힌 동안에도 높이가 흔들리지 않는다. */
function syncHeroBand(el) {
  el = el || document.getElementById("heroband");
  if (!el) return;
  const off = el.classList.contains("hb-off");
  const btn = el.querySelector(".hb-toggle");
  if (btn) {
    btn.setAttribute("aria-expanded", String(!off));
    btn.querySelector(".hb-lb").textContent = off ? "보기" : "가리기";
    btn.querySelector(".hb-eye").textContent = off ? "🙈" : "👁";
  }
}

// 카드 아무 데나 눌러도 접히고 펴진다 (버튼은 어디를 눌러야 하는지 알려 주는 표식).
document.addEventListener("click", (ev) => {
  const el = ev.target.closest("#heroband");
  if (!el) return;
  const off = el.classList.toggle("hb-off");
  localStorage.setItem(HB_HIDE_KEY, off ? "1" : "0");
  syncHeroBand(el);
});

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

