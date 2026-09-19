/* ---- 도넛 차트 (중앙 합계 + 범례 + 툴팁) ---- */
function arcPath(cx, cy, rO, rI, a0, a1) {
  const pt = (r, a) => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  const large = (a1 - a0) > Math.PI ? 1 : 0;
  const [x0, y0] = pt(rO, a0), [x1, y1] = pt(rO, a1);
  const [x2, y2] = pt(rI, a1), [x3, y3] = pt(rI, a0);
  return `M${x0} ${y0} A${rO} ${rO} 0 ${large} 1 ${x1} ${y1} L${x2} ${y2} A${rI} ${rI} 0 ${large} 0 ${x3} ${y3} Z`;
}

function donut(cell, spec) {
  // spec: {title, caption, center, centerLabel, slices:[{label,value,color,neg}], fmt}
  //   fmt: 값 표기 함수 (기본 억 단위). 생활비처럼 만원대 금액은 fmtMan을 넘긴다.
  const F = spec.fmt || fmtEok;
  cell.innerHTML = "";
  const h3 = document.createElement("h3"); h3.textContent = spec.title; cell.appendChild(h3);
  const cap = document.createElement("div"); cap.className = "cap"; cap.textContent = spec.caption || ""; cell.appendChild(cap);

  const slices = spec.slices.filter(s => Math.abs(s.value) > 0);
  const total = slices.reduce((s, x) => s + Math.abs(x.value), 0) || 1;
  const size = 200, cx = 100, cy = 100, rO = 84, rI = 55, gap = 0.025;
  const svg = el("svg", { viewBox: `0 0 ${size} ${size}`, style: "width:100%;max-width:200px;display:block" });
  // 상위 N개 조각에 값 병기 (마우스오버 없이) — spec.annotateTop
  const annFmt = spec.annFmt || F;
  const topIdx = new Set(slices.map((s, i) => i)
    .sort((a, b) => Math.abs(slices[b].value) - Math.abs(slices[a].value))
    .slice(0, spec.annotateTop || 0));
  let ang = -Math.PI / 2;
  slices.forEach((s, i) => {
    const frac = Math.abs(s.value) / total;
    const a0 = ang + gap / 2, a1 = ang + frac * 2 * Math.PI - gap / 2;
    const mid = ang + frac * Math.PI;
    if (a1 > a0) {
      const p = el("path", { d: arcPath(cx, cy, rO, rI, a0, a1), fill: s.color,
        stroke: "var(--surface-1)", "stroke-width": 1 }, svg);
      const sign = s.neg ? "−" : "";
      p.addEventListener("mousemove", ev => showTip(ev,
        `<b>${s.label}</b><br>${sign}${F(Math.abs(s.value))} (${(frac * 100).toFixed(1)}%)` +
        `<br><span style="color:var(--ink-muted)">${sign}${fmtWon(Math.abs(s.value))}</span>`));
      p.addEventListener("mouseleave", hideTip);
      // 상위 조각이고 충분히 크면 링 위에 값 표기
      if (topIdx.has(i) && frac > 0.06) {
        const rM = (rO + rI) / 2;
        el("text", { x: cx + rM * Math.cos(mid), y: cy + rM * Math.sin(mid),
          "text-anchor": "middle", "dominant-baseline": "central",
          "font-size": 9.5, "font-weight": 700, fill: "#fff",
          style: "paint-order:stroke; stroke:rgba(0,0,0,.28); stroke-width:2px;" }, svg)
          .textContent = annFmt(Math.abs(s.value));
      }
    }
    ang += frac * 2 * Math.PI;
  });
  // center를 안 넘기면 가운데를 비운다 — 같은 총액을 다른 도넛이 이미 보여줄 때
  // 여기선 비중만 읽으면 되기 때문. (넘기지 않았는데 F(undefined)를 찍어 'NaN억'이 뜨던 자리)
  if (spec.center != null) {
    el("text", { x: cx, y: cy - 1, "text-anchor": "middle", "font-size": 21, "font-weight": 700, fill: "var(--ink-1)" }, svg)
      .textContent = F(spec.center);
    el("text", { x: cx, y: cy + 16, "text-anchor": "middle", "font-size": 11, fill: "var(--ink-muted)" }, svg)
      .textContent = spec.centerLabel || "";
  }
  cell.appendChild(svg);

  const lg = document.createElement("div"); lg.className = "legend";
  for (const s of slices) {
    const span = document.createElement("span"); span.style.setProperty("--sw", s.color);
    const sign = s.neg ? "−" : "";
    // 생활비 등은 비중(%)보다 실제 금액이 중요 → spec.legendValue면 값으로 표기
    span.textContent = spec.legendValue
      ? `${s.label} ${sign}${F(Math.abs(s.value))}`
      : `${s.label} ${sign}${(Math.abs(s.value) / total * 100).toFixed(1)}%`;
    lg.appendChild(span);
  }
  cell.appendChild(lg);
}

function donutCell(parent) {
  const c = document.createElement("div"); c.className = "donut-cell";
  parent.appendChild(c); return c;
}

/* ---- 추이 라인 차트 (크로스헤어 + 툴팁) ---- */
function lineChart(container, points, opts) {
  // points: [{date, total}]
  if (points.length === 0) { container.textContent = "이력 데이터가 아직 없습니다."; return; }
  const W = Math.min(container.clientWidth || 900, 1000);
  const narrow = W < 520;                       // 폰
  const H = narrow ? 220 : 260;
  const m = { l: narrow ? 50 : 56, r: 16, t: 24, b: 26 };  // t: 점 위 값 라벨 자리
  const svg = el("svg", { width: "100%", viewBox: `0 0 ${W} ${H}`, class: "lc-svg" });
  const vals = points.map(p => p.total);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (lo === hi) { lo *= 0.97; hi *= 1.03; }
  // 아래쪽 여백은 폰에서 넉넉히 — 골짜기 점의 라벨을 점 아래에 두는데, x축 라벨과 부딪히지 않게.
  const span = hi - lo; lo -= span * (narrow ? 0.16 : 0.08); hi += span * 0.08;
  const xs = i => points.length === 1 ? (m.l + W - m.r) / 2
    : m.l + (W - m.l - m.r) * i / (points.length - 1);
  const ys = v => m.t + (H - m.t - m.b) * (1 - (v - lo) / (hi - lo));
  // gridlines + y labels
  for (let g = 0; g <= 3; g++) {
    const v = lo + (hi - lo) * g / 3, y = ys(v);
    el("line", { x1: m.l, x2: W - m.r, y1: y, y2: y, stroke: "var(--grid)", "stroke-width": 1 }, svg);
    const t = el("text", { x: m.l - 8, y: y + 4, "text-anchor": "end", "font-size": 11, fill: "var(--ink-muted)" }, svg);
    t.textContent = fmtEok(v);
  }
  // x labels — 연말은 "YYYY", 그 외는 "YY.MM". 연 단위 보기에서는 연도만 찍는다.
  const xlab = (opts && opts.yearly)
    ? date => date.slice(0, 4)
    : date => {
        const [y, mo, d] = date.split("-");
        return (mo === "12" && d === "31") ? y : y.slice(2) + "." + mo;
      };
  // 라벨 상자 — 값 라벨과 x축 라벨이 같은 규칙으로 서로를 피한다.
  // 종전엔 간격(34px)만 보고 솎아서, 왼쪽 정렬된 첫 라벨이 오른쪽으로 뻗는 것을 몰랐다.
  // 폰에서 '2021'과 '2023'이 붙어 '20212023'으로 읽혔다.
  const placed = [];
  const hit = b => placed.some(o => b.x0 < o.x1 && b.x1 > o.x0 && b.y0 < o.y1 && b.y1 > o.y0);
  const lastX = points.length - 1;
  const boxAt = (cx, anchor, w, y) => {
    const x0 = anchor === "start" ? cx - 2 : anchor === "end" ? cx - w + 2 : cx - w / 2;
    return { x0, x1: x0 + w, y0: y - 11, y1: y + 3 };
  };
  const anchorOf = i => i === 0 ? "start" : i === lastX ? "end" : "middle";
  // x축: 끝점 → 첫 점 → 나머지(가운데부터 고르게)를 넣을 수 있는 만큼. 이웃 사이 6px는 비운다.
  const xOrder = [lastX, 0];
  const per = (W - m.l - m.r) / Math.max(1, lastX);
  const stride = Math.max(1, Math.ceil(40 / Math.max(per, 1)));
  for (let i = lastX - stride; i > 0; i -= stride) xOrder.push(i);
  for (let i = 1; i < lastX; i++) xOrder.push(i);
  const xSeen = new Set();
  for (const i of xOrder) {
    if (xSeen.has(i)) continue; xSeen.add(i);
    const txt = xlab(points[i].date), a = anchorOf(i);
    const b = boxAt(xs(i), a, txt.length * 6.6 + 6, H - 6);
    const pad6 = { ...b, x0: b.x0 - 3, x1: b.x1 + 3 };
    if (hit(pad6)) continue;
    placed.push(pad6);
    el("text", { x: xs(i), y: H - 6, "text-anchor": a, "font-size": 11, fill: "var(--ink-muted)" }, svg)
      .textContent = txt;
  }
  if (points.length > 1) {
    const d = points.map((p, i) => (i ? "L" : "M") + xs(i).toFixed(1) + " " + ys(p.total).toFixed(1)).join(" ");
    el("path", { d, fill: "none", stroke: "var(--c-re)", "stroke-width": 2, "stroke-linejoin": "round" }, svg);
  }
  const dotR = points.length <= 40 ? (narrow ? 3 : 3.5) : 0;
  if (dotR) points.forEach((p, i) =>
    el("circle", { cx: xs(i), cy: ys(p.total), r: dotR, fill: "var(--c-re)", stroke: "var(--surface-1)", "stroke-width": 2 }, svg));

  // 점 위 값 라벨 — 겹치지 않는 것만 놓는다.
  // 종전엔 x축 라벨과 같은 간격(34px)으로 솎았는데, 값 라벨('18.71억')은 그보다 넓어서
  // 폰 폭에서 이웃끼리 포개졌다(2026-09 제보). 이제 라벨마다 실제 차지할 상자를 어림해
  // 이미 놓인 상자와 부딪히면 건너뛴다. 무엇을 먼저 놓을지는 '의미'로 정한다 —
  // 지금 값, 출발점, 최고점, 최저점이 먼저이고 나머지는 자리가 남을 때만.
  // 데스크톱은 자리가 넉넉해 종전처럼 전부 뜨고, 폰은 핵심만 남는다. 나머지는 스크럽으로 읽는다.
  const labW = s => (s.length - 1) * 6.7 + 11 + 6;   // 숫자·마침표 ≈6.7px, '억' ≈11px, 여백
  const iMax = vals.indexOf(Math.max(...vals)), iMin = vals.indexOf(Math.min(...vals));
  const order = [lastX, 0, iMax, iMin];
  for (let i = lastX - 1; i > 0; i--) order.push(i);   // 최근 쪽부터 채운다
  // 폰에서는 가로 한 칸에 값 라벨 하나만 — 높이가 달라 겹치지 않더라도 위아래로
  // 지그재그 쌓이면 빽빽하긴 마찬가지다. 비는 점은 판독창(스크럽)으로 읽는다.
  const vcols = [];
  const colHit = b => narrow && vcols.some(o => b.x0 < o.x1 + 6 && b.x1 > o.x0 - 6);
  const key = new Set([lastX, 0, iMax, iMin]);        // 반대편 재시도는 이 넷에게만
  const seen = new Set();
  for (const i of order) {
    if (seen.has(i)) continue; seen.add(i);
    const p = points[i], s = fmtEok(p.total), w = labW(s);
    const anchor = anchorOf(i), cx = xs(i);
    // 골짜기(양옆보다 낮은 점)는 라벨을 아래에 둔다 — 위에 두면 내려오고 올라가는 선에 얹힌다.
    const v = p.total, pv = points[i - 1], nx = points[i + 1];
    const valley = pv && nx && v < pv.total && v < nx.total;
    const above = ys(v) - 9, below = ys(v) + 19;
    let y = valley ? below : above;
    if (y === above && above < 12) y = below;           // 위에 자리가 없으면 점 아래로
    let box = boxAt(cx, anchor, w, y);
    if (!key.has(i) && colHit(box)) continue;          // 핵심 점은 칸 규칙에서 뺀다(실제로 겹칠 때만 비킨다)
    if (hit(box)) {                                      // 핵심 점만 반대쪽을 한 번 더 본다
      if (!key.has(i)) continue;
      y = y === above ? below : above;
      box = boxAt(cx, anchor, w, y);
      if (y < 12 || y > H - m.b + 2 || hit(box)) continue;
    }
    placed.push(box); vcols.push(box);
    el("text", { x: cx, y, "text-anchor": anchor, "font-size": 11, "font-weight": 600,
                 fill: i === lastX ? "var(--ink-1)" : "var(--ink-2)", class: "lc-lab" }, svg).textContent = s;
  }

  // 판독창 — 지금 가리키는 점의 시점·값·직전 대비. 기본은 가장 최근 점.
  // 종전엔 마우스를 올려야만 툴팁이 떴다. 폰에는 '올린다'가 없어 라벨이 빠진 점의 값을
  // 볼 방법이 없었다. 손가락으로 좌우로 끌면 판독창이 따라간다(주식 앱의 스크럽 방식).
  const read = document.createElement("div");
  read.className = "lc-read";
  const monthsBetween = (a, b) => {
    const [y1, m1] = a.split("-").map(Number), [y2, m2] = b.split("-").map(Number);
    return (y2 - y1) * 12 + (m2 - m1);
  };
  const when = (p, i) => {
    const [y, mo, d] = p.date.split("-");
    const base = (opts && opts.yearly) || (mo === "12" && d === "31") ? `${y}년` : `${y}.${mo}`;
    return i === lastX ? `${base} · 현재` : base;
  };
  const setRead = i => {
    const p = points[i], prev = points[i - 1];
    let delta = "";
    if (prev) {
      const dv = p.total - prev.total;
      const unit = monthsBetween(prev.date, p.date) <= 1 ? "전월" : "전년";
      const cls = dv > 0 ? "up" : dv < 0 ? "down" : "";
      delta = `<span class="lc-delta ${cls}">${unit} 대비 ${dv > 0 ? "▲" : dv < 0 ? "▼" : ""} ${fmtEok(Math.abs(dv))}</span>`;
    }
    read.innerHTML = `<span class="lc-when">${when(p, i)}</span><b class="lc-val">${fmtEok(p.total)}</b>${delta}`;
  };

  const cross = el("line", { y1: m.t, y2: H - m.b, stroke: "var(--baseline)", "stroke-width": 1, visibility: "hidden" }, svg);
  const hot = el("circle", { r: 5.5, fill: "var(--c-re)", stroke: "var(--surface-1)", "stroke-width": 2, visibility: "hidden" }, svg);
  const focus = i => {
    cross.setAttribute("x1", xs(i)); cross.setAttribute("x2", xs(i));
    cross.setAttribute("visibility", "visible");
    hot.setAttribute("cx", xs(i)); hot.setAttribute("cy", ys(points[i].total));
    hot.setAttribute("visibility", "visible");
    setRead(i);
  };
  const reset = () => {
    cross.setAttribute("visibility", "hidden"); hot.setAttribute("visibility", "hidden");
    setRead(lastX);
  };
  const nearest = ev => {
    const box = svg.getBoundingClientRect();
    const px = (ev.clientX - box.left) * W / box.width;
    let best = 0, bd = 1e9;
    points.forEach((_, i) => { const d = Math.abs(xs(i) - px); if (d < bd) { bd = d; best = i; } });
    return best;
  };
  // pointer 이벤트 하나로 마우스·터치를 함께 받는다. touch-action: pan-y(CSS)라 세로 스크롤은
  // 그대로 되고, 가로로 끌 때만 스크럽이 된다.
  svg.addEventListener("pointerdown", ev => focus(nearest(ev)));
  svg.addEventListener("pointermove", ev => {
    if (ev.pointerType === "mouse" || ev.buttons) focus(nearest(ev));
  });
  // 마우스는 벗어나면 지금 값으로 돌아간다. 손가락은 떼도 남겨 둔다 — 읽으려고 뗀 것이다.
  svg.addEventListener("pointerleave", ev => { if (ev.pointerType === "mouse") reset(); });
  svg.addEventListener("pointercancel", reset);

  reset();
  container.replaceChildren(read, svg);
}

/* ---- 연도별 소득·지출 ------------------------------------------------------
   원본은 시각화 탭 A56 '연도별 소득·지출 요약' 한 곳 — 연도를 더하려면 시트에
   행을 넣으면 된다. 여기서는 파생값만 만든다 (시트에 중복 저장하지 않는다).
     순잉여   = 총소득 − 총지출
     저축률   = 순잉여 / 총소득 × 100      (총소득 0이면 0 — 0으로 나누기 방지)
     월평균지출 = 총지출 / 개월수          (올해는 아직 12개월이 아니다)
   개월수를 12로 고정하지 않는 이유: 올해는 마감된 달까지만 집계돼 있어서
   12로 나누면 월평균이 실제보다 작아 보인다. */
function annualFlow(rows) {
  return (rows || []).map(r => {
    const income = Number(r.income) || 0, expense = Number(r.expense) || 0;
    const months = Math.min(12, Math.max(1, Number(r.months) || 12));
    const surplus = income - expense;
    return {
      year: Number(r.year), months, income, expense, surplus,
      savingsRate: income > 0 ? surplus / income * 100 : 0,
      monthlyExpense: Math.round(expense / months),
      partial: months < 12,
      note: r.note || "",
    };
  }).sort((a, b) => b.year - a.year);
}

function renderAnnualFlow(rows) {
  const sec = document.getElementById("flow-section");
  const list = annualFlow(rows);
  if (!list.length) { sec.style.display = "none"; return; }
  sec.style.display = "";

  const man = v => Math.round(v / 1e4).toLocaleString("ko-KR") + "만원";
  document.getElementById("flow-table").innerHTML =
    `<thead><tr><th>연도</th><th class="num">총소득</th><th class="num">총지출<span class="th-sub">투자 제외</span></th>
       <th class="num">순잉여자금</th><th class="num">저축률</th><th class="num">월평균 지출</th></tr></thead>
     <tbody>${list.map(r => `<tr>
       <td>${r.year}${r.partial ? `<span class="th-sub">1~${r.months}월</span>` : ""}</td>
       <td class="num">${man(r.income)}</td>
       <td class="num">${man(r.expense)}</td>
       <td class="num flow-surplus ${r.surplus >= 0 ? "delta-up" : "delta-down"}">${man(r.surplus)}</td>
       <td class="num flow-rate">${r.savingsRate.toFixed(1)}%</td>
       <td class="num">${man(r.monthlyExpense)}</td></tr>`).join("")}</tbody>`;

  // 해마다 가계부 양식이 달라 집계 근거가 다르다. 비교할 때 알고 봐야 하는 것만 적는다.
  const caveat = list.filter(r => /과소|누락/.test(r.note)).map(r => r.year);
  document.getElementById("flow-note").textContent =
    "투자 매수액과 전세보증금 같은 자금 이동은 지출에서 제외했습니다."
    + (caveat.length ? ` ${caveat.join("·")}년은 당시 가계부에 고정비(대출·보험·통신)가 항목으로 남아 있지 않아 지출이 실제보다 적게 잡혔습니다.` : "");
}

