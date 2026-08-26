/* ---- 월별 흐름 (스택 영역 + 크로스헤어) ---- */
function stackedArea(container, periods, series) {
  // series: [{label, color, values:[...]}]  values는 periods와 같은 길이
  container.innerHTML = "";
  const W = Math.min(container.clientWidth || 900, 1000), H = 260;
  const m = { l: 56, r: 16, t: 12, b: 26 };
  const n = periods.length;
  if (!n) { container.textContent = "이력이 아직 없습니다."; return; }
  const totals = periods.map((_, i) => series.reduce((s, x) => s + (x.values[i] || 0), 0));
  const hi = Math.max(...totals) * 1.08 || 1;
  const xs = i => n === 1 ? (m.l + W - m.r) / 2 : m.l + (W - m.l - m.r) * i / (n - 1);
  const ys = v => m.t + (H - m.t - m.b) * (1 - v / hi);
  const svg = el("svg", { width: "100%", viewBox: `0 0 ${W} ${H}` });

  for (let g = 0; g <= 3; g++) {
    const v = hi * g / 3, y = ys(v);
    el("line", { x1: m.l, x2: W - m.r, y1: y, y2: y, stroke: "var(--grid)", "stroke-width": 1 }, svg);
    el("text", { x: m.l - 8, y: y + 4, "text-anchor": "end", "font-size": 11, fill: "var(--ink-muted)" }, svg)
      .textContent = fmtEok(v);
  }
  const step = Math.max(1, Math.ceil(n / 8));
  for (let i = 0; i < n; i += step)
    el("text", { x: xs(i), y: H - 6, "text-anchor": "middle", "font-size": 11, fill: "var(--ink-muted)" }, svg)
      .textContent = periods[i].label;

  // 누적 스택 (아래→위)
  const base = new Array(n).fill(0);
  for (const s of series) {
    const top = base.map((b, i) => b + (s.values[i] || 0));
    const up = top.map((v, i) => `${xs(i).toFixed(1)} ${ys(v).toFixed(1)}`);
    const down = base.map((v, i) => `${xs(i).toFixed(1)} ${ys(v).toFixed(1)}`).reverse();
    el("path", { d: `M${up.join(" L")} L${down.join(" L")} Z`, fill: s.color,
                 "fill-opacity": 0.85, stroke: "var(--surface-1)", "stroke-width": 0.5 }, svg);
    for (let i = 0; i < n; i++) base[i] = top[i];
  }

  const cross = el("line", { y1: m.t, y2: H - m.b, stroke: "var(--baseline)", "stroke-width": 1, visibility: "hidden" }, svg);
  svg.addEventListener("mousemove", ev => {
    const box = svg.getBoundingClientRect();
    const px = (ev.clientX - box.left) * W / box.width;
    let best = 0, bd = 1e9;
    for (let i = 0; i < n; i++) { const d = Math.abs(xs(i) - px); if (d < bd) { bd = d; best = i; } }
    cross.setAttribute("x1", xs(best)); cross.setAttribute("x2", xs(best));
    cross.setAttribute("visibility", "visible");
    const rows = series.map(s =>
      `<span style="color:${s.color}">■</span> ${s.label} ${fmtEok(s.values[best] || 0)}`).reverse().join("<br>");
    showTip(ev, `<b>${periods[best].label}</b><br>${rows}<br><b>합계 ${fmtEok(totals[best])}</b>`);
  });
  svg.addEventListener("mouseleave", () => { cross.setAttribute("visibility", "hidden"); hideTip(); });
  container.appendChild(svg);

  const lg = document.createElement("div"); lg.className = "legend";
  for (const s of series) {
    const sp = document.createElement("span"); sp.style.setProperty("--sw", s.color);
    sp.textContent = s.label; lg.appendChild(sp);
  }
  container.appendChild(lg);
}

function renderMonthly(mon) {
  const card = document.getElementById("fin-trend-card");
  if (!mon || !mon.periods || !mon.periods.length) { card.style.display = "none"; return; }
  card.style.display = "";
  const periods = mon.periods, accts = mon.accounts || [];
  const sumBy = (key, val) => periods.map((_, i) =>
    accts.filter(a => a[key] === val).reduce((s, a) => s + (a.values[i] || 0), 0));
  const SERIES = {
    owner: [
      { label: "우현", color: "var(--c-us)", values: sumBy("owner", "우현") },
      { label: "규리", color: "var(--c-vi)", values: sumBy("owner", "규리") },
    ],
    group: [
      { label: "연금성", color: "var(--c-re)", values: sumBy("group", "연금성") },
      { label: "유동성", color: "var(--c-kr)", values: sumBy("group", "유동성") },
    ],
  };
  const draw = mode => stackedArea(document.getElementById("fin-trend"), periods, SERIES[mode]);
  draw("owner");
  document.querySelectorAll("#fin-trend-seg .seg-btn").forEach(b =>
    b.addEventListener("click", () => {
      document.querySelectorAll("#fin-trend-seg .seg-btn").forEach(x => x.classList.toggle("on", x === b));
      draw(b.dataset.mode);
    }));
}

/* ---- 오늘의 체크포인트 (분당부부 모닝 리포트) ---- */
const esc = s => String(s ?? "").replace(/[&<>"]/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ---- 오늘의 금융자산 (브리핑용) --------------------------------------------
   현재값은 실시간(★주식계좌 GOOGLEFINANCE)을 쓰고, 비교 기준만 과거에서 가져온다.
     전일 — history.csv의 '오늘 이전 마지막 날' 주식 행 (소유자별로 쌓여 있다)
     전월·전년 — asset_history의 계좌:소유자 (★월별자산/★연도별자산)
   전일만 history를 쓰는 이유: prev_day는 총자산·순자산만 있고 소유자별이 없다. */
function finDailyByOwner(histText, todayKey) {
  const byDate = new Map();
  for (const line of (histText || "").trim().split("\n").slice(1)) {
    if (!line) continue;
    const c = line.split(",");            // date,kind,name,owner,category,value_krw
    if (c.length < 6 || c[4] !== "주식") continue;
    const d = c[0];
    if (d >= todayKey) continue;          // 오늘 기록분은 비교 대상이 아니다
    if (!byDate.has(d)) byDate.set(d, {});
    const o = byDate.get(d);
    o[c[3]] = (o[c[3]] || 0) + Number(c[5] || 0);
  }
  const days = [...byDate.keys()].sort();
  return days.length ? { date: days[days.length - 1], owners: byDate.get(days[days.length - 1]) } : null;
}

/* 브리핑 상단 금융자산 카드. 부부 합계 + 사람별, 각각 전일·전월·전년 대비. */
function finTodayHtml(fin, hist, ah) {
  const own = {};
  for (const h of ((fin && fin.holdings) || [])) own[h.owner] = (own[h.owner] || 0) + h.value_krw;
  const people = ["우현", "규리"].filter(p => own[p]);
  if (!people.length) return "";

  const A = (ah && ah.assets) || {};
  const base = p => ({
    d1: hist && hist.owners ? hist.owners[p] : null,
    m1: (A["계좌:" + p] || {}).m1 || null,
    y1: (A["계좌:" + p] || {}).y1 || null,
  });
  const sum = k => people.reduce((s, p) => { const v = base(p)[k]; return v == null ? s : s + v; }, 0) || null;

  // 자산 현황 KPI 카드와 같은 형식으로 — 라벨 / 큰 숫자 / 그 아래 전일·전월·전년.
  // 종전엔 한 줄에 [이름 | 금액 | 증감]을 늘어놓아 가운데가 휑했다. 같은 성격의 숫자는
  // 같은 모양으로 보이는 게 읽기 쉽다.
  const deltas = (cur, b) => {
    const parts = [["전일", b.d1], ["전월", b.m1], ["전년", b.y1]].map(([lb, prev]) => {
      if (!prev) return "";
      const d = cur - prev, pct = d / prev * 100;
      return `<span class="kd"><i>${lb}</i> <b class="${d >= 0 ? "delta-up" : "delta-down"}">`
           + `${d >= 0 ? "▲" : "▼"}${Math.abs(pct).toFixed(1)}%</b></span>`;
    }).filter(Boolean);
    return parts.length ? `<span class="kpi-deltas">${parts.join("")}</span>` : "";
  };

  const total = people.reduce((s, p) => s + own[p], 0);
  const card = (label, cur, b, hero) =>
    kpiCard(esc(label), eokMan(cur), deltas(cur, b), hero);

  // '전일'이 정말 어제인지 — 일별 잡이 밀리면 그저께 값과 비교하게 된다. 그때만 밝힌다.
  const y = new Date(Date.now() + 9 * 3600e3 - 864e5).toISOString().slice(0, 10);
  const stale = hist && hist.date !== y
    ? `<div class="cp-mkt-note">전일 비교 기준이 ${esc(hist.date.slice(5))}입니다 — 기록이 하루 이상 밀렸습니다</div>`
    : "";

  return `<section class="card">
    <h2>우리 부부 현재 금융자산</h2>
    <div class="cards" style="margin-bottom:0">
      ${card("부부 합산", total, { d1: sum("d1"), m1: sum("m1"), y1: sum("y1") }, true)}
      ${people.map(p => card(p, own[p], base(p))).join("")}
    </div>
    ${stale}
  </section>`;
}

/* 오늘의 운세 카드 — 브리핑 바로 뒤에 놓으려고 따로 뺐다 (없으면 빈 문자열). */
/* 옛 리포트에 남아 있는 '💡 오늘의 한 수:' 같은 딱지를 걷어내 말로 잇는다.
   프롬프트를 고쳐 새 리포트부터는 안 나오지만, 이미 시트에 저장된 것들이 하루이틀 남는다. */
const fortuneTalk = t => String(t || "")
  .replace(/\s*[💡▶]\s*(오늘|이번\s*주)의?\s*한\s*수\s*[:：]\s*/g, " ")
  .replace(/\s*💰\s*/g, " ")
  .replace(/\n+/g, " ")
  .replace(/\s{2,}/g, " ")
  .trim();

function fortuneHtml(f) {
  if (!f) return "";
  const person = (emoji, name, p) => !p || !p.body ? "" : `<div class="fortune-person">
    <div class="fortune-head"><span class="fortune-name">${emoji} ${name}</span>
      <span class="fortune-stars">${esc(p.stars || "")}</span></div>
    <div class="fortune-body">${esc(fortuneTalk([p.body, p.money].filter(Boolean).join(" ")))}</div>
    ${p.work ? `<div class="fortune-work">💼 ${esc(fortuneTalk(p.work))}</div>` : ""}
    ${(p.lucky_hour || p.lucky_number) ? `<div class="luck">🍀 ${[p.lucky_hour, p.lucky_color, p.lucky_number ? "숫자 " + p.lucky_number : ""].filter(Boolean).map(esc).join(" · ")}</div>` : ""}
  </div>`;
  // 일진·음력·오행은 표가 아니라 할머니가 먼저 꺼내는 말이다. 도입부와 한 문단으로 잇는다.
  const day = [f.ganzi && `${f.ganzi} ${f.zodiac}의 날`.trim(), f.lunar, f.interaction]
    .filter(Boolean).join(" · ");
  // 부부 이야기와 축원도 딱지 없이 — 마지막은 할머니가 손 모아 비는 말로 닫는다.
  const closing = [f.couple, f.blessing].filter(Boolean).join(" ");
  return `<section class="card"><h2>오늘의 운세</h2>
    ${day ? `<div class="cp-date" style="margin-top:0">${esc(day)}</div>` : ""}
    ${f.intro ? `<div class="fortune-open">${esc(fortuneTalk(f.intro))}</div>` : ""}
    ${person("🐰", "우현", f.woohyun)}${person("🐷", "규리", f.kyuri)}
    ${closing ? `<div class="fortune-close">${esc(fortuneTalk(closing))}</div>` : ""}
  </section>`;
}

function renderCheckpoint(cp, finBlock) {
  const body = document.getElementById("cp-body");
  if (!cp || !cp.date_label) {
    body.innerHTML = `<section class="card"><h2>오늘의 체크포인트</h2>
      <div class="goal-sub">아직 리포트가 도착하지 않았어요. 매일 아침 모닝 리포트가 발송되면 여기에 표시됩니다.</div>
      </section>`;
    return;
  }
  const pct = v => (v == null || Math.abs(v) < 0.005) ? "0.00%" : (v > 0 ? "+" : "") + v.toFixed(2) + "%";
  const cls = v => v > 0 ? "delta-up" : v < 0 ? "delta-down" : "";
  const px = (v, unit) => v == null ? "—"
    : unit === "pt" ? v.toLocaleString("ko-KR", { maximumFractionDigits: 0 }) + "pt"
    : unit === "$" ? "$" + v.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : "₩" + v.toLocaleString("ko-KR", { maximumFractionDigits: 0 });
  // 등락을 '몇 원'으로 — 현재가와 %로 역산 (base=price/(1+p/100), Δ=price-base).
  // 환율은 %보다 실제 원(₩) 변동이 직관적이라는 요청(2026-07-21)으로 환율 표만 이 모드를 쓴다.
  const wonD = (price, p) => (price == null || p == null) ? "—"
    : (() => {
        const d = price * (p / 100) / (1 + p / 100);
        return Math.abs(d) < 0.05 ? "0원"
          : (d > 0 ? "+" : "−") + Math.abs(d).toLocaleString("ko-KR", { maximumFractionDigits: 1 }) + "원";
      })();
  // 증권사 시세 화면식 표 — 1일/1주/1개월/1년. 스냅샷 폴백은 1일만 있어 나머지는 '—'.
  // mode "won": 등락을 % 대신 실제 원(₩) 변동으로 표기 (환율 전용).
  const HZ = [["d1", "1일"], ["w1", "1주"], ["m1", "1개월"], ["y1", "1년"]];
  // 시세 3종(미국·국내·환율)을 한 표로 합치기 위한 행 빌더 — 종목명 폭이 달라도
  // 하나의 <table>이라 현재가·등락 열이 자동 정렬된다. 환율만 mode="won"(원 변동).
  // 1일만 칩(배경 틴트)으로 승격 — 오늘 어땠는지가 먼저 눈에 걸려야 한다.
  // 나머지 기간은 조용한 수치로 둬서, 넷이 같은 목소리로 떠들지 않게 한다.
  const mktCell = (i, k, mode) => {
    const p = i[k] !== undefined ? i[k] : (k === "d1" ? i.change_pct : null);
    if (p == null) return `<td style="color:var(--ink-muted)">—</td>`;
    const v = mode === "won" ? wonD(i.price ?? i.rate, p) : pct(p);
    if (k === "d1") {
      const dir = Math.abs(p) < 0.005 ? "flat" : (p > 0 ? "up" : "dn");
      return `<td><span class="delta-chip ${dir}">${v}</span></td>`;
    }
    return `<td class="${cls(p)}"><b>${v}</b></td>`;
  };
  const mktRow = (i, mode) => `<tr>
    <td>${esc(i.name)}${i.stale ? `<span class="mkt-asof">⚠️${esc((i.asof || "").slice(5))} 종가</span>` : ""}</td>
    <td class="mkt-px">${px(i.price ?? i.rate, i.unit || "₩")}</td>
    ${HZ.map(([k]) => mktCell(i, k, mode)).join("")}
  </tr>`;
  const mktGroupHead = t => `<tr class="mkt-grp"><td colspan="${2 + HZ.length}">${esc(t)}</td></tr>`;

  let h = "";
  if (cp.stale) {
    // 하루 밀린 것과 며칠 밀린 것은 말이 달라야 한다. 운세는 날짜가 곧 내용이라
    // '어제 것'이라는 사실이 분명히 보여야 오늘 일진으로 착각하지 않는다.
    const when = cp.age_days === 1 ? "어제" : `${cp.age_days}일 전`;
    h += `<div class="cp-stale">⚠️ ${when}(${esc(cp.date_label)}) 리포트입니다 —`
       + ` 오늘 발송이 밀렸어요. <b>운세·날씨는 어제 기준</b>이고 시세·뉴스는 실시간입니다.</div>`;
  }

  // 브리핑(인사말·날씨·운세)은 모닝 리포트가 하루 한 번 만든다 — 시세·뉴스(실시간)와 달리
  // 오늘 것이 아닐 수 있다. 아직 안 왔으면 '언제 오는지'까지 말해 준다.
  //   리포트는 '미국장 마감(16:00 ET) + 1시간'에 온다 — 서머타임이면 KST 06시,
  //   아니면 07시. 종전엔 '6시대 갱신'이라고만 적어 두어, 겨울에 6시에 열어 보고
  //   '왜 안 바뀌었지' 하게 됐다. 브라우저에서 같은 규칙으로 계산해 사실대로 적는다.
  const genDay = (cp.generated_at || "").slice(0, 10);
  const nowKST = new Date(Date.now() + 9 * 3600e3);
  const today = nowKST.toISOString().slice(0, 10);          // KST 기준 오늘
  // 뉴욕이 서머타임이면 마감이 KST 05시라 리포트가 06시, 아니면 마감 06시라 07시.
  // 오프셋(EDT −4 / EST −5)으로 판별한다 — 서버와 같은 규칙이라 문구가 늘 실제와 맞는다.
  const nyOffset = (() => {
    const s = new Date().toLocaleString("en-US", {
      timeZone: "America/New_York", timeZoneName: "shortOffset" });
    const m = s.match(/GMT([+-]\d+)/);
    return m ? Math.abs(Number(m[1])) : 5;   // 못 읽으면 겨울(늦은 쪽)로 보수적 가정
  })();
  const sendHour = nyOffset === 4 ? 6 : 7;   // 미국장 마감 + 1시간
  const beforeSend = nowKST.getUTCHours() < sendHour;
  const briefNote = (genDay && genDay !== today)
    ? `<div class="cp-pending">${beforeSend
        ? `오늘 브리핑은 <b>오전 ${sendHour}시경</b> 도착합니다`
        : `오늘 브리핑이 아직 도착하지 않았습니다 <b>(예정 오전 ${sendHour}시)</b>`
      } · 아래는 ${esc(cp.date_label)} 내용입니다. 시세·뉴스는 실시간입니다.</div>`
    : "";

  // 인사 + 날씨 — 날씨는 한 덩어리 텍스트로 오지만 그대로 흘리면 읽히지 않는다.
  //   1줄차(오늘 기온·미세먼지)는 크게, 2줄차(시간대별)는 '·' 기준으로 잘라 칩으로 흩는다.
  const wx = String(cp.weather || "").split("\n").map(s => s.trim()).filter(Boolean);
  const wxHtml = wx.length ? `<div class="cp-wx">
      <div class="cp-wx-main">${esc(wx[0])}</div>
      ${wx.slice(1).map(line => `<div class="cp-wx-chips">${
        line.split("·").map(p => p.trim()).filter(Boolean)
            .map(p => `<span class="wx-chip">${esc(p)}</span>`).join("")
      }</div>`).join("")}
    </div>` : "";
  // 날씨가 맨 위 — 아침에 창밖부터 확인하는 순서 그대로.
  // 그다음 날짜·인사·시장 요약을 한 덩어리 인사말로 붙인다. 종전엔 제목/인사/요약이
  // 세 조각으로 떨어져 같은 이야기를 세 번 시작하는 것처럼 읽혔다.
  const hello = [cp.greeting, cp.summary].filter(Boolean).join(" ");
  // 안내는 인사말보다 먼저 — 왜 어제 내용이 보이는지 알고 읽어야 오해가 없다
  h += `<section class="card">
    ${wxHtml}
    <div class="cp-date">${esc(cp.date_label)}</div>
    ${briefNote}
    ${hello ? `<div class="cp-hero">${esc(hello)}</div>` : ""}
  </section>`;

  // 오늘의 금융자산 — 운세보다 위. 아침에 가장 먼저 확인하는 숫자다.
  h += finBlock || "";

  // 운세 — 시세보다 먼저. '오늘 하루가 어떤 날인가'를 먼저 읽고 숫자로 넘어가는 흐름.
  h += fortuneHtml(cp.fortune);

  // 지수 · 환율 — 제목은 고정("미국 지수" 등)으로, 실시간 여부는 기준시각 배지로 알린다.
  // cp.live_at 은 30분 시세 잡(live.enc)이 붙었을 때만 채워진다. 없으면 07:00 스냅샷.
  const badge = cp.live_at
    ? `<span class="live-badge on"><span class="dot"></span>실시간 ${esc(cp.live_at)} 기준</span>`
    : `<span class="live-badge off">오늘 아침 스냅샷${cp.generated_at ? ` · ${esc((cp.generated_at).slice(11,16))}` : ""}</span>`;
  const fg = cp.fear_greed || {};
  const fgLine = fg.score != null
    ? `공포탐욕 <b>${fg.score}</b> (${esc(fg.label || "")})${fg.vix ? ` · VIX ${fg.vix.toFixed(1)}` : ""}` : "";
  const usAsof = (cp.us || []).map(i => i.asof).filter(Boolean).sort().pop();

  // 미국·국내·환율을 한 표로 통합 — 그룹 소제목 행으로 구분, 환율만 원(₩) 변동 모드.
  // 공포탐욕지수는 요청대로 표 아래 별도 문구로 그대로 남긴다.
  const mktGroups = [
    ["미국 지수", cp.us, undefined],
    ["국내 지수·ETF", cp.kr, undefined],
    ["환율", cp.fx, "won"],
  ].filter(g => (g[1] || []).length);
  // 시세·매크로·뉴스는 '참고 자료' 성격이라 넓은 화면에서 2단으로 접는다.
  // 브리핑·자산·운세(위쪽)는 읽는 순서가 있어 1단을 유지 — 여기만 폭을 쓴다.
  h += `<div class="cp-cols"><div class="cp-col">`;

  if (mktGroups.length) {
    const rows = mktGroups.map(([t, arr, mode]) =>
      mktGroupHead(t) + arr.map(i => mktRow(i, mode)).join("")).join("");
    const hasFx = mktGroups.some(g => g[2] === "won");
    h += `<section class="card">
      <div class="cp-mkt-head"><h2>시세</h2>${badge}</div>
      <div style="overflow-x:auto"><table class="mkt mkt-unified">
        <thead><tr><th>종목</th><th>현재가</th>${HZ.map(([, l]) => `<th>${l}</th>`).join("")}</tr></thead>
        <tbody>${rows}</tbody></table></div>
      ${usAsof ? `<div class="cp-mkt-note">미국 지수 ${esc(usAsof.slice(5))} 종가 기준</div>` : ""}
      ${fgLine ? `<div class="cp-mkt-note">${fgLine}</div>` : ""}
    </section>`;
  }
  if (cp.macro_dday) h += `<section class="card"><h2>매크로 캘린더</h2>
    <div style="font-size:var(--fs-body)">${esc(cp.macro_dday)}</div></section>`;

  h += `</div><div class="cp-col">`;   // 좌열 닫고 우열 열기 — 뉴스는 오른쪽

  // 뉴스 — 30분마다 관심 주제(보유 ETF·미국증시·환율금리·FIRE)로 갱신되는 실시간 피드.
  if ((cp.news || []).length) h += `<section class="card">
    <div class="cp-mkt-head"><h2>관심 뉴스</h2>${cp.news_live ? badge : ""}</div>
    ${cp.news.map((n, i) => `<div class="news-item">
      <div class="news-title">${i + 1}. ${n.link ? `<a href="${esc(n.link)}" target="_blank" rel="noopener">${esc(n.title)}</a>` : esc(n.title)}</div>
      <div class="news-meta">${n.tag ? `<span class="news-tag">${esc(n.tag)}</span>` : ""}${n.source ? esc(n.source) : ""}${n.published ? ` · ${esc(n.published)}` : ""}</div>
      ${n.insight ? `<div class="news-insight">→ ${esc(n.insight)}</div>` : ""}
    </div>`).join("")}
    </section>`;

  h += `</div></div>`;   // .cp-col · .cp-cols 닫기

  if ((cp.data_warnings || []).length)
    h += `<div class="goal-sub">⚠️ 데이터 점검: ${esc(cp.data_warnings.join(" · "))}</div>`;
  body.innerHTML = h;
}

/* ---- 월별 배당 (계좌별 스택 막대 + 세전/세후 토글) ---- */
function barStack(container, labels, series, kinds) {
  // kinds: 월별 'actual'(기준일 지나 확정) / 'est'(작년 실적 기반 추정) — 추정은 흐리게 칠한다
  container.innerHTML = "";
  const W = Math.min(container.clientWidth || 900, 1000), H = 250;
  const m = { l: 56, r: 12, t: 26, b: 26 };  // t: 막대 위 합계 라벨 자리
  const n = labels.length;
  const totals = labels.map((_, i) => series.reduce((s, x) => s + (x.values[i] || 0), 0));
  const hi = Math.max(...totals, 1) * 1.12;
  const bw = (W - m.l - m.r) / n * 0.62;
  const xc = i => m.l + (W - m.l - m.r) * (i + 0.5) / n;
  const ys = v => m.t + (H - m.t - m.b) * (1 - v / hi);
  const svg = el("svg", { width: "100%", viewBox: `0 0 ${W} ${H}` });
  for (let g = 0; g <= 3; g++) {
    const v = hi * g / 3, y = ys(v);
    el("line", { x1: m.l, x2: W - m.r, y1: y, y2: y, stroke: "var(--grid)", "stroke-width": 1 }, svg);
    el("text", { x: m.l - 8, y: y + 4, "text-anchor": "end", "font-size": 11, fill: "var(--ink-muted)" }, svg)
      .textContent = fmtMan(v);
  }
  labels.forEach((L, i) =>
    el("text", { x: xc(i), y: H - 6, "text-anchor": "middle", "font-size": 11, fill: "var(--ink-muted)" }, svg)
      .textContent = L);
  const base = new Array(n).fill(0);
  for (const s of series) {
    for (let i = 0; i < n; i++) {
      const v = s.values[i] || 0;
      if (v <= 0) continue;
      const y0 = ys(base[i]), y1 = ys(base[i] + v);
      const est = kinds && kinds[i] === "est";
      const rect = el("rect", { x: xc(i) - bw / 2, y: y1, width: bw, height: Math.max(1, y0 - y1),
                                fill: s.color, "fill-opacity": est ? 0.3 : 0.9 }, svg);
      rect.addEventListener("mousemove", ev => showTip(ev,
        `<b>${labels[i]}</b>${est ? " <span style=\"color:var(--ink-muted)\">(예상)</span>" : ""}` +
        `<br><span style="color:${s.color}">■</span> ${s.label} ${fmtMan(v)}` +
        `<br><b>합계 ${fmtMan(totals[i])}</b>`));
      rect.addEventListener("mouseleave", hideTip);
      base[i] += v;
    }
  }
  // 막대 위 월 합계 — 마우스오버 없이도 바로 읽히게
  totals.forEach((t, i) => {
    if (t <= 0) return;
    el("text", { x: xc(i), y: ys(t) - 6, "text-anchor": "middle", "font-size": 11, "font-weight": 600,
                 fill: kinds && kinds[i] === "est" ? "var(--ink-muted)" : "var(--ink-1)" }, svg)
      .textContent = fmtMan(t);
  });
  container.appendChild(svg);
  const lg = document.createElement("div"); lg.className = "legend";
  for (const s of series) {
    const sp = document.createElement("span"); sp.style.setProperty("--sw", s.color);
    sp.textContent = s.label; lg.appendChild(sp);
  }
  container.appendChild(lg);
}

const ACCT_COLORS = ["var(--c-us)", "var(--c-vi)", "var(--c-re)", "var(--c-kr)",
                     "var(--c-cash)", "var(--c-debt)", "var(--baseline)"];

function renderDivMonthly(H, year) {
  const card = document.getElementById("fin-divmo-card");
  const paying = H.filter(h => h.div_krw > 0);
  if (!paying.length || !paying[0].div_months) { card.style.display = "none"; return; }
  card.style.display = "";
  const MONTHS = [...Array(12)].map((_, i) => `${i + 1}월`);
  // 월별 확정/추정 — 백엔드가 종목마다 찍어준 값을 그대로 접는다 (기준일 지난 달 = 확정)
  const kinds = MONTHS.map((_, i) =>
    paying.some(h => (h.div_kinds || [])[i] === "est") ? "est"
      : paying.some(h => (h.div_kinds || [])[i] === "actual") ? "actual" : "");
  const estFrom = kinds.indexOf("est");

  // 계좌(소유자 포함)별 월별 집계
  const accs = new Map();
  for (const h of paying) {
    const key = `${h.owner} ${h.account}`;
    const a = accs.get(key) || { label: key, gross: new Array(12).fill(0), net: new Array(12).fill(0), rate: h.tax_rate, note: h.tax_note };
    for (let i = 0; i < 12; i++) {
      const g = h.div_months[i] || 0;
      a.gross[i] += g;
      a.net[i] += g * (1 - h.tax_rate);
    }
    accs.set(key, a);
  }
  const list = [...accs.values()].sort((a, b) =>
    b.gross.reduce((s, v) => s + v, 0) - a.gross.reduce((s, v) => s + v, 0));

  const draw = mode => {
    const series = list.map((a, i) => ({
      label: a.label, color: ACCT_COLORS[i % ACCT_COLORS.length],
      values: (mode === "net" ? a.net : a.gross).map(Math.round),
    }));
    barStack(document.getElementById("fin-divmo"), MONTHS, series, kinds);
    const rows = list.map((a, i) => {
      const vals = mode === "net" ? a.net : a.gross;
      const tot = vals.reduce((s, v) => s + v, 0);
      return `<tr>
        <td class="name"><span class="chip" style="background:${ACCT_COLORS[i % ACCT_COLORS.length]}"></span>${a.label}</td>
        ${vals.map(v => `<td style="color:${v > 0 ? "var(--ink-1)" : "var(--ink-muted)"}">${v > 0 ? fmtMan(v) : "—"}</td>`).join("")}
        <td><b>${fmtMan(tot)}</b></td></tr>`;
    }).join("");
    const totRow = MONTHS.map((_, i) =>
      list.reduce((s, a) => s + (mode === "net" ? a.net : a.gross)[i], 0));
    document.getElementById("fin-divmo-tbl").innerHTML = `
      <thead><tr><th>계좌</th>${MONTHS.map((m, i) =>
        `<th${kinds[i] === "est" ? ' style="color:var(--ink-muted)"' : ""}>${m}</th>`).join("")}<th>${year}년</th></tr></thead>
      <tbody>${rows}
        <tr><td class="name"><b>합계</b></td>
          ${totRow.map(v => `<td><b>${v > 0 ? fmtMan(v) : "—"}</b></td>`).join("")}
          <td><b>${fmtMan(totRow.reduce((s, v) => s + v, 0))}</b></td></tr>
      </tbody>`;
  };
  draw("net");
  document.querySelectorAll("#fin-divmo-seg .seg-btn").forEach(b =>
    b.addEventListener("click", () => {
      document.querySelectorAll("#fin-divmo-seg .seg-btn").forEach(x => x.classList.toggle("on", x === b));
      draw(b.dataset.mode);
    }));

  const notes = [...new Set(list.map(a => a.note))];
  document.getElementById("fin-divmo-note").innerHTML =
    `실제 지급월 기준`
    + (estFrom >= 0 ? ` · ${estFrom + 1}월부터 흐린 막대는 작년 실적 기반 추정` : "")
    + ` · 세율 ${notes.join(" · ")}`;
}

function renderFinancial(fin) {
  const H = (fin && fin.holdings) || [];
  if (!H.length) {
    document.getElementById("tab-financial").innerHTML =
      `<section class="card"><h2>금융자산</h2>
       <div class="goal-sub">★주식계좌 시트를 불러오지 못했어요.</div></section>`;
    return;
  }
  const uh = H.filter(h => h.owner === "우현"), gr = H.filter(h => h.owner === "규리");
  const totAll = sum(H), divAll = sum(H, h => h.div_krw);
  const pens = sum(H.filter(h => h.group === "연금성")), liq = totAll - pens;
  const year = (fin && fin.year) || new Date().getFullYear();
  // 확정 = 이미 기준일이 지나 금액이 정해진 배당. 나머지는 작년 실적 기반 추정.
  const divDone = H.reduce((s, h) => s + (h.div_months || [])
    .reduce((t, v, i) => t + ((h.div_kinds || [])[i] === "actual" ? v : 0), 0), 0);

  // KPI
  document.getElementById("fin-kpis").innerHTML =
    kpiCard("금융자산 총액", fmtEok(totAll), `우현 ${fmtEok(sum(uh))} · 규리 ${fmtEok(sum(gr))}`, true) +
    kpiCard(`${year}년 예상 배당금`, fmtMan(divAll),
      `확정 ${fmtMan(divDone)} + 예상 ${fmtMan(divAll - divDone)} · 수익률 ${(divAll / totAll * 100).toFixed(2)}%`) +
    kpiCard("연금성 비중", (pens / totAll * 100).toFixed(1) + "%", `연금성 ${fmtEok(pens)} · 유동성 ${fmtEok(liq)}`);

  // 포트폴리오 도넛 — 같은 돈을 '실제 종목'과 '추종 지수' 두 기준으로. 토글로 갈아끼운다.
  //   지수별은 국내 상장 ETF도 실제 추종 지수로 묶어, 이름이 달라도 같은 지수에 몰린
  //   노출을 드러낸다 (SCHD와 TIGER 미국배당다우존스는 다른 종목이지만 같은 지수).
  const dc = document.getElementById("fin-donuts");
  const drawDonuts = mode => {
    const f = mode === "index" ? indexDonut : portfolioDonut;
    dc.innerHTML = "";
    f(donutCell(dc), "우리 (부부 합산)", H);
    f(donutCell(dc), "우현", uh);
    f(donutCell(dc), "규리", gr);
    document.getElementById("fin-idx-note").textContent =
      mode === "index" ? "채권혼합50은 나스닥100 절반만 반영" : "";
  };
  drawDonuts("holding");
  const dseg = document.getElementById("fin-donut-seg");
  dseg.onclick = ev => {
    const b = ev.target.closest(".seg-btn"); if (!b) return;
    for (const x of dseg.querySelectorAll(".seg-btn")) x.classList.toggle("on", x === b);
    drawDonuts(b.dataset.mode);
  };

  // 연금성 vs 유동성
  const g = (hs, kind) => sum(hs.filter(h => h.group === kind));
  document.getElementById("fin-groups").innerHTML =
    stackBar("우리", pens, liq) +
    stackBar("우현", g(uh, "연금성"), g(uh, "유동성")) +
    stackBar("규리", g(gr, "연금성"), g(gr, "유동성"));

  // 배당 카드
  const divCard = (who, hs) => {
    const gross = sum(hs, h => h.div_krw), net = sum(hs, h => h.div_net_krw), base = sum(hs);
    const tax = gross - net;
    return `<div class="div-card"><div class="who">${who}</div>
      <div class="amt">${fmtMan(net)}</div>
      <div class="mo">세후 · 월평균 ${fmtMan(net / 12)} · 수익률 ${base > 0 ? (net / base * 100).toFixed(2) : "0.00"}%</div>
      <div class="mo" style="margin-top:4px">세전 ${fmtMan(gross)}${tax > 0 ? ` · 세금 −${fmtMan(tax)}` : " · 세금 없음"}</div></div>`;
  };
  document.getElementById("fin-div").innerHTML =
    divCard("우리 (부부 합산)", H) + divCard("우현", uh) + divCard("규리", gr);
  document.getElementById("fin-div-h2").textContent = `${year}년 예상 배당금`;

  renderDivMonthly(H, year);

  // 계좌별 상세
  const am = new Map();
  for (const h of H) {
    const k = h.owner + "|" + h.account;
    const c = am.get(k) || { owner: h.owner, account: h.account, group: h.group,
                             value: 0, div: 0, divNet: 0, note: h.tax_note };
    c.value += h.value_krw; c.div += h.div_krw; c.divNet += h.div_net_krw;
    am.set(k, c);
  }
  const rows = [...am.values()].filter(a => a.value > 0).sort((a, b) => b.value - a.value).map(a => `
    <tr><td class="name">${a.account}</td><td>${a.owner}</td>
      <td><span class="chip" style="background:${a.group === "연금성" ? "var(--c-vi)" : "var(--c-us)"}"></span>${a.group}</td>
      <td><b>${fmtEok(a.value)}</b></td>
      <td style="color:var(--ink-muted)">${a.div > 0 ? fmtMan(a.div) : "—"}</td>
      <td>${a.div > 0 ? `<b>${fmtMan(a.divNet)}</b>` : "—"}</td>
      <td style="color:var(--ink-muted)">${a.div > 0 ? a.note : "—"}</td></tr>`).join("");
  document.getElementById("fin-detail").innerHTML =
    `<thead><tr><th>계좌</th><th>소유</th><th>성격</th><th>평가액</th><th>${year}년 배당(세전)</th><th>${year}년 배당(세후)</th><th>세율 적용</th></tr></thead><tbody>${rows}</tbody>`;
}

