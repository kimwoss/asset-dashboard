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
  const W = Math.min(container.clientWidth || 900, 1000), H = 260;
  const m = { l: 56, r: 16, t: 24, b: 26 };  // t: 점 위 값 라벨 자리
  const svg = el("svg", { width: "100%", viewBox: `0 0 ${W} ${H}` });
  if (points.length === 0) { container.textContent = "이력 데이터가 아직 없습니다."; return; }
  const vals = points.map(p => p.total);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (lo === hi) { lo *= 0.97; hi *= 1.03; }
  const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
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
  // x labels — 연말은 "YYYY", 그 외는 "YY.MM". 겹치지 않게 최대 ~8개 균등 표시.
  // 연 단위 보기에서는 날짜가 연말이 아니어도(올해 점은 오늘) 연도만 찍는다.
  const xlab = (opts && opts.yearly)
    ? date => date.slice(0, 4)
    : date => {
        const [y, mo, d] = date.split("-");
        return (mo === "12" && d === "31") ? y : y.slice(2) + "." + mo;
      };
  // 라벨은 매 기간 표시. 다만 폭이 부족하면(연 단위로 늘어나면) 겹치지 않게 솎는다.
  const per = (W - m.l - m.r) / Math.max(1, points.length - 1);
  const step = Math.max(1, Math.ceil(34 / Math.max(per, 1)));
  const xIdx = new Set();
  for (let i = 0; i < points.length; i += step) xIdx.add(i);
  xIdx.add(points.length - 1);
  for (const i of xIdx) {
    const t = el("text", { x: xs(i), y: H - 6, "text-anchor": "middle", "font-size": 11, fill: "var(--ink-muted)" }, svg);
    t.textContent = xlab(points[i].date);
  }
  if (points.length > 1) {
    const d = points.map((p, i) => (i ? "L" : "M") + xs(i).toFixed(1) + " " + ys(p.total).toFixed(1)).join(" ");
    el("path", { d, fill: "none", stroke: "var(--c-re)", "stroke-width": 2, "stroke-linejoin": "round" }, svg);
  }
  const dotR = points.length <= 40 ? 3.5 : 0;
  if (dotR) points.forEach((p, i) =>
    el("circle", { cx: xs(i), cy: ys(p.total), r: dotR, fill: "var(--c-re)", stroke: "var(--surface-1)", "stroke-width": 2 }, svg));
  // 점 위 순자산 값 — 마우스오버 없이도 바로 읽히게 (촘촘하면 라벨 간격만큼 솎음)
  for (const i of xIdx) {
    const p = points[i];
    el("text", { x: xs(i), y: ys(p.total) - 9,
                 "text-anchor": i === 0 ? "start" : i === points.length - 1 ? "end" : "middle",
                 "font-size": 11, "font-weight": 600, fill: "var(--ink-1)" }, svg)
      .textContent = fmtEok(p.total);
  }
  // crosshair
  const cross = el("line", { y1: m.t, y2: H - m.b, stroke: "var(--baseline)", "stroke-width": 1, visibility: "hidden" }, svg);
  const hot = el("circle", { r: 5, fill: "var(--c-re)", stroke: "var(--surface-1)", "stroke-width": 2, visibility: "hidden" }, svg);
  svg.addEventListener("mousemove", ev => {
    const box = svg.getBoundingClientRect();
    const px = (ev.clientX - box.left) * W / box.width;
    let best = 0, bd = 1e9;
    points.forEach((_, i) => { const d = Math.abs(xs(i) - px); if (d < bd) { bd = d; best = i; } });
    const p = points[best];
    cross.setAttribute("x1", xs(best)); cross.setAttribute("x2", xs(best));
    cross.setAttribute("visibility", "visible");
    hot.setAttribute("cx", xs(best)); hot.setAttribute("cy", ys(p.total));
    hot.setAttribute("visibility", "visible");
    showTip(ev, `<b>${p.date}</b><br>순자산 ${fmtEok(p.total)}<br><span style="color:var(--ink-muted)">${fmtWon(p.total)}</span>`);
  });
  svg.addEventListener("mouseleave", () => { cross.setAttribute("visibility", "hidden"); hot.setAttribute("visibility", "hidden"); hideTip(); });
  container.replaceChildren(svg);
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

