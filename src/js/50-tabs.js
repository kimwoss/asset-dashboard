/* ---- 살고싶은 도시 (🌍이주 대시보드 · Numbeo 기반) ---- */
const ctShort = n => String(n || "").split(",")[0].trim();          // "New York, NY, US" → "New York"
const ctCountry = n => { const p = String(n || "").split(","); return p.slice(1).join(",").trim(); };

/* ---- 다음 후보집 ((ing)2027년 오피스텔) ----
   시트가 원본. 여기는 '기준을 통과한 매물'과 '아직 매물이 없는 타입'을 나눠 보여준다.
   환산전세는 시트 수식과 같은 식(보증금 + 월세/40 × 1억)이라 두 화면 숫자가 어긋나지 않는다. */
function renderOfficetel(of) {
  const tabBtn = document.querySelector('.tab[data-tab="officetel"]');
  if (!of || !of.items || !of.items.length) { if (tabBtn) tabBtn.style.display = "none"; return; }

  const eok = v => v == null ? "\u2014" : (v / 10000).toFixed(2) + "\uc5b5";
  const won = v => v == null ? "" : Number(v).toLocaleString();
  const cond = x => x.monthly ? won(x.deposit) + " / " + won(x.monthly) : "\uc804\uc138 " + won(x.deposit);
  const s = of.summary || {};
  document.getElementById("of-kpis").innerHTML =
      kpiCard("\uae30\uc900 \ud1b5\uacfc", (s.ok ?? 0) + "\uac74", "\ub4f1\ub85d \ub9e4\ubb3c " + (s.listed ?? 0) + "\uac74 \uc911", true)
    + kpiCard("\ucd5c\uc800 \ud658\uc0b0\uc804\uc138", eok(s.min_conv), "\uc0c1\ud55c " + eok(of.cap_man) + " \u00b7 \uc804\uc6a9 " + of.area_min + "\ud3c9\u2191")
    + kpiCard("\ud6c4\ubcf4 \uc624\ud53c\uc2a4\ud154", (s.buildings ?? 0) + "\uacf3", "\ud0c0\uc785 " + (s.total ?? 0) + "\uc885");

  // 별점이 높은 순 → 같으면 싼 순. 중개사가 훑는 순서와 같게.
  const live = of.items.filter(x => x.ok).sort((p1, p2) =>
    (p2.stars || "").length - (p1.stars || "").length || p1.converted - p2.converted);
  const asof = live.map(x => x.asof).filter(Boolean).sort().pop();
  document.getElementById("of-asof").textContent = asof ? "\ucd5c\uadfc \ud655\uc778 " + asof : "";
  document.getElementById("of-criteria").textContent = of.criteria || "";

  const goLink = u => u ? '<a class="of-go" href="' + esc(u) + '" target="_blank" rel="noopener">\ubcf4\uae30 \u2197</a>' : "";

  // \ubcc4\uc810 \u2014 4\uc2dc\uac04 \uc7a1\uc774 \ub9e4\uae34 \uac12\uc744 \uadf8\ub300\ub85c \ubcf4\uc5ec\uc900\ub2e4. \uadfc\uac70\ub294 title\ub85c \ubd99\uc5ec \uc65c \ubcc4\uc774 \ubd99\uc5c8\ub294\uc9c0
  // \ubc14\ub85c \ud655\uc778\ud560 \uc218 \uc788\uac8c \ud55c\ub2e4(\ubcc4\ub9cc \ubcf4\uace0 \ubbff\uc744 \uac12\uc774 \uc544\ub2c8\ub2e4).
  // 확인일 — 호가는 사람이 붙여넣은 시점이 곧 신선도다. 며칠 지났는지 함께 보여주고,
  // 2주가 넘으면 흐리게 눕힌다 (이미 나간 매물일 수 있다).
  const asofCell = v => {
    const m = String(v || "").trim().match(/([0-9]{4})-([0-9]{2})-([0-9]{2})/);
    if (!m) return '<td style="color:var(--ink-muted)">\u2014</td>';
    const d = new Date(+m[1], +m[2] - 1, +m[3]);
    // 경과 '시간'이 아니라 달력 '날짜' 차이로 센다 — Date.now()로 재면 오늘 확인한
    // 매물이 시각에 따라 '어제'로 표시된다.
    const t0 = new Date(); t0.setHours(0, 0, 0, 0);
    const days = Math.max(0, Math.round((t0 - d) / 86400000));
    const label = days === 0 ? "오늘" : days === 1 ? "어제" : days + "일 전";
    return '<td class="of-asof' + (days > 14 ? " stale" : "") + '" title="' + esc(m[0]) + '">'
      + (+m[2]) + "/" + (+m[3]) + '<span class="ago">' + label + "</span></td>";
  };

  const starTag = x => x.stars
    ? '<span class="of-star s' + x.stars.length + '" title="' + esc(x.why || "") + '">'
      + x.stars + "</span>" : "";

  // \ud0c0\uc785 \uce78 \u2014 \ubcf4\uc5ec\uc904 \uc81c\uc6d0(\ud3c9\uba74\ub3c4\u00b7\uba74\uc801\u00b7\uc804\uc6a9\ub960\u00b7\uc138\ub300\uc218)\uc774 \ud558\ub098\ub77c\ub3c4 \uc788\uc73c\uba74 \ub204\ub97c \uc218 \uc788\uac8c.
  const M2 = 3.305785;
  const hasSpec = x => !!(x.plan || x.ratio || x.supply || x.sale);
  const typeCell = (x, i) =>
    hasSpec(x) ? '<span class="of-type" data-g="' + i + '">' + esc(x.type || "—") + " \u25be</span>"
               : '<span class="of-type none">' + esc(x.type || "—") + "</span>";

  // \ucd5c\uadfc \uc2dc\uc138 \uce78 \u2014 \uad6d\ud1a0\ubd80 \uc2e4\uac70\ub798\uac00 \uc788\uc73c\uba74 \ub204\ub97c \uc218 \uc788\uac8c, \uc5c6\uc73c\uba74 \uadf8\ub300\ub85c \ub454\ub2e4.
  const dealsOf = x => (of.deals || {})[x.bucket || ""] || [];
  const dealCell = (x, i) => {
    const n = dealsOf(x).length;
    const t = esc(x.recent || (n ? n + "\uac74" : "\u2014"));
    return n ? '<span class="of-deal" data-g="' + i + '">' + t + " \u25be</span>"
             : '<span class="of-deal none">' + t + "</span>";
  };

  document.getElementById("of-live").innerHTML =
    "<thead><tr><th>\uc624\ud53c\uc2a4\ud154</th><th>\ud0c0\uc785</th><th>\uc804\uc6a9</th><th>\uad6c\uc870</th>"
    + "<th>\ubcf4\uc99d\uae08/\uc6d4\uc138</th><th>\ud658\uc0b0\uc804\uc138</th><th>\uce35\u00b7\ud5a5</th><th>\ud655\uc778\uc77c</th><th></th></tr></thead><tbody>"
    + (live.length ? live.map(x =>
        '<tr><td class="name">' + starTag(x) + esc(x.name)
        + '<span class="mkt-asof">' + esc(x.region || "") + "</span></td>"
        + "<td>" + esc(x.type || "—") + "</td><td>" + (x.area ? x.area.toFixed(2) + "\ud3c9" : "\u2014") + "</td>"
        + "<td>" + esc(x.rooms || "—") + "</td><td>" + esc(cond(x)) + "</td>"
        + '<td class="mkt-px"><b>' + eok(x.converted) + "</b></td>"
        + "<td>" + esc([x.floor, x.facing].filter(Boolean).join(" \u00b7 ")) + "</td>"
        + asofCell(x.asof)
        + "<td>" + goLink(x.link) + "</td></tr>").join("")
      : '<tr><td colspan="9" style="color:var(--ink-muted)">\uae30\uc900\uc744 \ud1b5\uacfc\ud55c \ub9e4\ubb3c\uc774 \uc5c6\uc2b5\ub2c8\ub2e4</td></tr>')
    + "</tbody>";

  // \ud0c0\uc785 \uce74\ud0c8\ub85c\uadf8 \u2014 \uc624\ud53c\uc2a4\ud154\u00b7\ud0c0\uc785 \ud55c \uc904\ub85c \uc811\uace0, \ub9e4\ubb3c \uc218\ub97c \ub20c\ub7ec \ud38c\uce5c\ub2e4.
  const groups = new Map();
  for (const x of of.items) {
    const k = x.name + " " + x.type;
    if (!groups.has(k)) groups.set(k, { spec: {}, list: [] });
    const g = groups.get(k);
    if (x.listed) g.list.push(x);
    // 같은 타입의 여러 행에서 '비어 있지 않은 값'만 골라 제원을 합친다.
    // 종전엔 첫 행을 통째로 spec으로 삼아, 그 행이 매물 행이라 구조·세대수가 비어 있으면
    // 카탈로그 칸이 빈 채로 나왔다(힐스테이트과천중앙 69F 구조 공란). 타입 제원은
    // 어느 행에 적혀 있든 같은 값이므로, 채워진 걸 쓰는 게 맞다.
    for (const [key, v] of Object.entries(x))
      if (g.spec[key] === undefined || g.spec[key] === "" || g.spec[key] === null)
        if (v !== "" && v !== null && v !== undefined) g.spec[key] = v;
  }
  const rows = [...groups.values()].sort((g1, g2) =>
    (g1.spec.name || "").localeCompare(g2.spec.name || "") || (g1.spec.area || 0) - (g2.spec.area || 0));

  const body = document.getElementById("of-wait");
  body.innerHTML =
    "<thead><tr><th>\uc624\ud53c\uc2a4\ud154</th><th>\ud0c0\uc785</th><th>\uc804\uc6a9</th><th>\uad6c\uc870</th>"
    + "<th>\uc138\ub300\uc218</th><th>\uac15\ub0a8\uc5ed</th><th>\ucd5c\uadfc \uc2dc\uc138</th><th>\ub9e4\ubb3c \uc218</th></tr></thead><tbody>"
    + rows.map((g, i) => {
        const x = g.spec, n = g.list.length;
        const cnt = n
          ? '<span class="of-cnt of-more" data-g="' + i + '">' + n + "\uac74 \u25be</span>"
          : '<span class="of-cnt zero">0</span>';
        const head = '<tr><td class="name">' + esc(x.name) + "</td><td>" + typeCell(x, i) + "</td>"
          + "<td>" + (x.area ? x.area.toFixed(2) + "\ud3c9" : "\u2014") + "</td>"
          + "<td>" + esc(x.rooms || "—") + "</td>"
          + "<td>" + (x.units ? Math.round(x.units).toLocaleString() + "\uc2e4" : "\u2014") + "</td>"
          + "<td>" + esc(x.toGangnam || "—") + "</td>"
          + "<td>" + dealCell(x, i) + "</td><td>" + cnt + "</td></tr>";
        const sub = '<tr class="of-sub" id="of-sub-' + i + '" style="display:none"><td colspan="8">'
          + g.list.sort((v1, v2) => (v1.converted || 0) - (v2.converted || 0)).map(v =>
              '<div class="of-line">' + starTag(v) + "<b>" + eok(v.converted) + "</b><span>" + esc(cond(v)) + "</span>"
              + '<span style="color:var(--ink-muted)">' + esc([v.floor, v.facing].filter(Boolean).join(" \u00b7 ")) + "</span>"
              + '<span style="color:var(--ink-muted)">' + esc(v.asof || "") + "</span>"
              + goLink(v.link) + "</div>").join("")
          + "</td></tr>";
        const dl = dealsOf(x);
        const deal = !dl.length ? "" :
          '<tr class="of-sub" id="of-deal-' + i + '" style="display:none"><td colspan="8">'
          + '<div class="of-dl"><div class="r hd"><span>계약일</span><span>전용</span><span>층</span>'
          + "<span>보증금 / 월세</span><b>환산전세</b></div>"
          + dl.map(t =>
              '<div class="r"><span>' + esc(t.date || "—") + "</span>"
              + "<span>" + t.area.toFixed(2) + "평</span>"
              + "<span>" + (t.floor ? Math.round(t.floor) + "층" : "—") + "</span>"
              + "<span>" + (t.monthly
                  ? t.deposit.toLocaleString() + " / " + t.monthly.toLocaleString()
                  : "전세 " + t.deposit.toLocaleString()) + "</span>"
              + "<b>" + eok(t.converted) + "</b></div>").join("")
          + '<div class="src">국토교통부 실거래가 · 최근 12개월 (동·호 정보는 공개되지 않습니다)</div>'
          + "</div></td></tr>";
        // 타입 제원 + 평면도. 평면도는 네이버 CDN을 그대로 가리키므로 막힐 수 있다 —
        // 막히면 onerror가 '네이버에서 보기' 링크로 물러난다.
        const spec = !hasSpec(x) ? "" :
          '<tr class="of-sub" id="of-spec-' + i + '" style="display:none"><td colspan="8">'
          + '<div class="of-spec">'
          + (x.plan ? '<div class="of-plan"><img src="' + esc(x.plan) + '" alt="'
              + esc(x.name + " " + x.type) + ' 평면도" loading="lazy" referrerpolicy="no-referrer"'
              + " onerror=\"this.style.display='none';this.nextElementSibling.style.display=''\">"
              + '<a class="of-go fail" style="display:none" href="' + esc(x.plan)
              + '" target="_blank" rel="noopener">평면도 열기 ↗</a></div>' : "")
          + "<dl>"
          + (x.supply ? "<dt>공급</dt><dd>" + x.supply.toFixed(2) + "평 · "
              + (x.supply * M2).toFixed(2) + "㎡</dd>" : "")
          + (x.area ? "<dt>전용</dt><dd>" + x.area.toFixed(2) + "평 · "
              + (x.area * M2).toFixed(2) + "㎡</dd>" : "")
          + (x.ratio ? "<dt>전용률</dt><dd>" + Math.round(x.ratio * 100) + "%</dd>" : "")
          + (x.units ? "<dt>세대수</dt><dd>" + Math.round(x.units).toLocaleString() + "실</dd>" : "")
          + (x.rooms ? "<dt>구조</dt><dd>" + esc(x.rooms) + "</dd>" : "")
          + (x.sale ? "<dt>매매 호가</dt><dd>" + esc(x.sale) + "</dd>" : "")
          + "</dl></div></td></tr>";
        return head + spec + sub + deal;
      }).join("") + "</tbody>";

  // 세 칸이 각각 제 몫을 편다 — 타입 → 평면도·제원, 최근 시세 → 실거래, 매물 수 → 호가.
  const OF_PANEL = { "of-type": "of-spec-", "of-deal": "of-deal-", "of-more": "of-sub-" };
  body.onclick = ev => {
    const b = ev.target.closest(".of-type, .of-deal, .of-more");
    if (!b || b.classList.contains("none")) return;
    const pre = Object.entries(OF_PANEL).find(([c]) => b.classList.contains(c));
    const sub = pre && document.getElementById(pre[1] + b.dataset.g);
    if (!sub) return;
    const open = sub.style.display !== "none";
    sub.style.display = open ? "none" : "";
    b.textContent = b.textContent.replace(open ? "\u25b4" : "\u25be", open ? "\u25be" : "\u25b4");
  };
}

function renderCities(ct, net) {
  const tabBtn = document.querySelector('.tab[data-tab="cities"]');
  if (!ct || !ct.cities || !ct.cities.length || !ct.seoul) { if (tabBtn) tabBtn.style.display = "none"; return; }
  const seoul = ct.seoul;
  const byCost = [...ct.cities].sort((a, b) => a.avg_monthly - b.avg_monthly);
  const reachable = ct.cities.filter(c => c.fire_target > 0 && net >= c.fire_target).length;
  const vsSeoul = c => seoul.avg_monthly ? c.avg_monthly / seoul.avg_monthly * 100 : 0;

  // 지금 순자산으로 감당되는 생활비 — 시트가 도시별 FIRE 필요자금을 낼 때 쓰는 것과 같은
  // 비례식(서울 기준)을 그대로 쓴다. 그래야 아래 막대·달성률과 숫자가 어긋나지 않는다.
  //   순자산 / 서울 FIRE필요 = 달성률 → 그 비율만큼의 연 예산이 지금 감당 가능한 몫
  // '가장 저렴한 도시가 얼마'보다 '내가 지금 얼마까지 쓸 수 있나'가 판단에 바로 쓰인다.
  const afford = seoul.fire_target ? seoul.annual_budget * (net / seoul.fire_target) : 0;

  // KPI — 서울 기준 · 지금 감당 가능한 생활비 · 은퇴 가능한 도시 수
  document.getElementById("ct-kpis").innerHTML =
    kpiCard("서울 (기준)", fmtMan(seoul.avg_monthly) + "/월", `FIRE 필요 ${fmtEok(seoul.fire_target)} · 연 ${fmtMan(seoul.annual_budget)}`, true) +
    kpiCard("현재 순자산 기준", fmtMan(afford / 12) + "/월", `현재 순자산 ${fmtEok(net)} · 연 ${fmtMan(afford)}`) +
    // 순자산 금액은 바로 왼쪽 '현재 순자산 기준' 카드가 이미 적었다 — 여기선 판정 기준만
    kpiCard("지금 순자산으로 은퇴 가능", `${reachable} / ${ct.cities.length}곳`, "도시별 FIRE 필요자금 대비");

  // 서울 대비 가로 막대 (도시명이 길어 가로가 읽기 좋다). 서울은 기준선으로 표시.
  const rows = [{ ...seoul, _seoul: true }, ...byCost];
  const maxV = Math.max(...rows.map(r => r.avg_monthly)) * 1.02;
  document.getElementById("ct-bars").innerHTML = rows.map(c => {
    const w = c.avg_monthly / maxV * 100, vs = vsSeoul(c);
    const col = c._seoul ? "var(--baseline)" : vs <= 100 ? "var(--pos)" : "var(--accent)";
    const tag = c._seoul ? "기준" : (vs <= 100 ? `-${(100 - vs).toFixed(0)}%` : `+${(vs - 100).toFixed(0)}%`);
    return `<div class="ct-bar-row">
      <div class="ct-bar-name" title="${esc(c.name)}">${esc(ctShort(c.name))}${c._seoul ? " ⭐" : ""}</div>
      <div class="ct-bar-track"><div class="ct-bar-fill" style="width:${w}%;background:${col}"></div>
        <span class="ct-bar-val">${fmtMan(c.avg_monthly)} <b style="color:${col}">${tag}</b></span></div>
    </div>`;
  }).join("");
  document.getElementById("ct-bars-note").textContent =
    "Numbeo 물가 기준 · 초록=서울보다 저렴 · 파랑=비쌈";

  // 도시 선택 → 상세 (카테고리별 서울 대비 + 실시간 순자산 달성률)
  const pick = document.getElementById("ct-pick");
  pick.innerHTML = byCost.map((c, i) =>
    `<button class="seg-btn${i === 0 ? " on" : ""}" data-i="${i}">${esc(ctShort(c.name))}</button>`).join("");
  const drawDetail = c => {
    const pctFire = c.fire_target ? net / c.fire_target * 100 : 0;
    const cats = (ct.categories || []).map((m, k) => ({
      name: m.name, group: m.group, seoul: seoul.categories[k] || 0, city: c.categories[k] || 0,
    })).filter(x => x.seoul || x.city).sort((a, b) => b.city - a.city);
    const gTag = g => g ? `<span class="ct-gtag">${esc(g)}</span>` : "";
    const catRows = cats.map(x => {
      const r = x.seoul ? x.city / x.seoul : 1, dn = r < 1;
      return `<tr><td class="name">${esc(x.name)} ${gTag(x.group)}</td>
        <td>${fmtMan(x.seoul)}</td><td><b>${fmtMan(x.city)}</b></td>
        <td class="${dn ? "delta-up" : r > 1 ? "delta-down" : ""}">×${r.toFixed(2)}</td></tr>`;
    }).join("");
    document.getElementById("ct-detail").innerHTML = `
      <div class="ct-detail-head">
        <div><div class="ct-detail-city">${esc(ctShort(c.name))}</div>
          <div class="ct-detail-sub">${esc(ctCountry(c.name))} · ${esc(c.status || "")}</div></div>
        <div class="ct-detail-fire">
          <div class="ct-detail-fire-pct" style="color:${pctFire >= 100 ? "var(--up)" : "var(--c-us)"}">${pctFire.toFixed(1)}%</div>
          <div class="ct-detail-sub">FIRE 달성 (필요 ${fmtEok(c.fire_target)})</div></div>
      </div>
      <div class="ct-facts">
        <div class="fact"><div class="l">월 생활비</div><div class="v">${fmtMan(c.avg_monthly)}</div><div class="s">서울 대비 ${vsSeoul(c).toFixed(0)}%</div></div>
        <div class="fact"><div class="l">연간 사용예산</div><div class="v">${fmtMan(c.annual_budget)}</div><div class="s">월 생활비×12 + 연 고정비</div></div>
        <div class="fact"><div class="l">월 변동 생활비</div><div class="v">${fmtMan(c.monthly_total)}</div><div class="s">현지 물가 연동 항목</div></div>
        <div class="fact"><div class="l">연 고정비</div><div class="v">${fmtMan(c.annual_fixed)}</div><div class="s">한국 귀속·수동 항목</div></div>
      </div>
      <div style="overflow-x:auto;margin-top:14px"><table class="mkt">
        <thead><tr><th>월간 항목</th><th>서울</th><th>${esc(ctShort(c.name))}</th><th>배율</th></tr></thead>
        <tbody>${catRows}</tbody></table></div>`;
  };
  drawDetail(byCost[0]);
  pick.addEventListener("click", ev => {
    const b = ev.target.closest(".seg-btn"); if (!b) return;
    for (const x of pick.querySelectorAll(".seg-btn")) x.classList.toggle("on", x === b);
    drawDetail(byCost[+b.dataset.i]);
  });

  // 전체 표
  const trow = c => {
    const pctFire = c.fire_target ? net / c.fire_target * 100 : 0, vs = vsSeoul(c);
    return `<tr>
      <td class="name">${esc(ctShort(c.name))}<span class="mkt-asof">${esc(ctCountry(c.name))}</span></td>
      <td><b>${fmtMan(c.avg_monthly)}</b></td>
      <td class="${vs <= 100 ? "delta-up" : "delta-down"}">${vs.toFixed(0)}%</td>
      <td>${fmtMan(c.annual_budget)}</td>
      <td>${fmtEok(c.fire_target)}</td>
      <td class="${pctFire >= 100 ? "delta-up" : ""}"><b>${pctFire.toFixed(0)}%</b></td></tr>`;
  };
  document.getElementById("ct-table").innerHTML = `
    <thead><tr><th>도시</th><th>월 생활비</th><th>서울대비</th><th>연 예산</th><th>FIRE 필요</th><th>달성률</th></tr></thead>
    <tbody><tr style="background:var(--page)"><td class="name"><b>서울 ⭐</b></td>
      <td><b>${fmtMan(seoul.avg_monthly)}</b></td><td>100%</td><td>${fmtMan(seoul.annual_budget)}</td>
      <td>${fmtEok(seoul.fire_target)}</td><td><b>${seoul.fire_target ? (net / seoul.fire_target * 100).toFixed(0) : 0}%</b></td></tr>
      ${byCost.map(trow).join("")}</tbody>`;
  document.getElementById("ct-note").innerHTML =
    "달성률은 현재 순자산으로 재계산 · 도시 추가·변경은 시트 🌍이주 대시보드 4행에 입력하면 반영됩니다.";
}

let _tabsInited = false;
/* ---- 은퇴 100세 지도 (시뮬레이션) ---- */
function simChart(container, series, mode, retireAge, depAge) {
  container.innerHTML = "";
  const key = mode === "nominal" ? "net" : "real_net";
  // 소진 이후는 비현실적 부채나선 — 소진 +2년까지만 그린다 (0 교차를 보여주되 꼬리 절단)
  const cut = depAge ? depAge + 2 : series[series.length - 1].age;
  const pts = series.filter(s => s.age <= cut);
  const W = Math.min(container.clientWidth || 900, 1000), H = 300;
  const m = { l: 52, r: 14, t: 16, b: 42 };
  const ages = pts.map(p => p.age), vals = pts.map(p => p[key]);
  const aMin = ages[0], aMax = ages[ages.length - 1];
  let hi = Math.max(...vals, 0), lo = Math.min(...vals, 0);
  hi *= 1.08; lo = lo < 0 ? lo * 1.08 : 0;
  const xs = a => m.l + (W - m.l - m.r) * (a - aMin) / (aMax - aMin);
  const ys = v => m.t + (H - m.t - m.b) * (1 - (v - lo) / (hi - lo));
  const svg = el("svg", { width: "100%", viewBox: `0 0 ${W} ${H}` });

  // y 그리드 (억 단위)
  const step = hi > 30e8 ? 10e8 : 5e8;
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) {
    const y = ys(v);
    el("line", { x1: m.l, x2: W - m.r, y1: y, y2: y, stroke: "var(--grid)", "stroke-width": v === 0 ? 1.5 : 1,
                 ...(v === 0 ? { stroke: "var(--baseline)" } : {}) }, svg);
    el("text", { x: m.l - 8, y: y + 4, "text-anchor": "end", "font-size": 11, fill: "var(--ink-muted)" }, svg)
      .textContent = fmtEok(v);
  }
  // x 축 나이 (10년 간격)
  for (let a = Math.ceil(aMin / 10) * 10; a <= aMax; a += 10)
    el("text", { x: xs(a), y: H - 22, "text-anchor": "middle", "font-size": 11, fill: "var(--ink-muted)" }, svg)
      .textContent = a + "세";

  // 폭락·회복 구간 띠 — 라인보다 먼저 깔아야 선이 띠 위로 온다.
  // 순환을 꺼 두면 전부 '평상'이라 아무것도 그려지지 않는다(종전 화면과 동일).
  const half = (W - m.l - m.r) / Math.max(aMax - aMin, 1) / 2;
  for (const p of pts) {
    if (p.cycle !== "폭락" && p.cycle !== "회복") continue;
    el("rect", { x: xs(p.age) - half, y: m.t, width: half * 2, height: H - m.t - m.b,
                 fill: p.cycle === "폭락" ? "var(--neg)" : "var(--pos)",
                 "fill-opacity": p.cycle === "폭락" ? 0.16 : 0.07 }, svg);
  }

  // 은퇴·소진 마커
  const marker = (age, label, color) => {
    if (!age || age < aMin || age > aMax) return;
    el("line", { x1: xs(age), x2: xs(age), y1: m.t, y2: H - m.b, stroke: color, "stroke-width": 1,
                 "stroke-dasharray": "3 3", opacity: 0.7 }, svg);
    el("text", { x: xs(age), y: H - 6, "text-anchor": "middle", "font-size": 10.5, "font-weight": 600, fill: color }, svg)
      .textContent = `${label} ${age}세`;
  };

  // 면적 + 라인
  const line = pts.map(p => `${xs(p.age).toFixed(1)} ${ys(p[key]).toFixed(1)}`);
  const area = `M${xs(aMin).toFixed(1)} ${ys(0).toFixed(1)} L${line.join(" L")} L${xs(aMax).toFixed(1)} ${ys(0).toFixed(1)} Z`;
  el("path", { d: area, fill: "var(--c-us)", "fill-opacity": 0.12 }, svg);
  el("path", { d: `M${line.join(" L")}`, fill: "none", stroke: "var(--c-us)", "stroke-width": 2.5 }, svg);
  marker(retireAge, "은퇴", "var(--c-vi)");
  marker(depAge, "소진", "var(--neg)");

  // 크로스헤어
  const cross = el("line", { y1: m.t, y2: H - m.b, stroke: "var(--baseline)", "stroke-width": 1, visibility: "hidden" }, svg);
  const dot = el("circle", { r: 4, fill: "var(--c-us)", stroke: "var(--surface-1)", "stroke-width": 1.5, visibility: "hidden" }, svg);
  svg.addEventListener("mousemove", ev => {
    const box = svg.getBoundingClientRect();
    const a = Math.round(aMin + (aMax - aMin) * ((ev.clientX - box.left) * W / box.width - m.l) / (W - m.l - m.r));
    const p = pts.find(x => x.age === a); if (!p) return;
    cross.setAttribute("x1", xs(a)); cross.setAttribute("x2", xs(a)); cross.setAttribute("visibility", "visible");
    dot.setAttribute("cx", xs(a)); dot.setAttribute("cy", ys(p[key])); dot.setAttribute("visibility", "visible");
    showTip(ev, `<b>${p.age}세</b> (${esc(p.phase)})<br>${mode === "nominal" ? "순자산" : "실질 순자산"} ${fmtEok(p[key])}` +
      (p.cycle && p.cycle !== "평상"
        ? `<br><b style="color:${p.cycle === "폭락" ? "var(--neg)" : "var(--pos)"}">${p.cycle}</b>`
          + ` <span style="color:var(--ink-muted)">수익률 ${(p.rate * 100).toFixed(1)}%</span>`
          + (p.spend_mult < 1
              ? ` <span style="color:var(--pos)">생활비 −${Math.round((1 - p.spend_mult) * 100)}%</span>` : "")
        : "") +
      (p.spend ? `<br><span style="color:var(--ink-muted)">연지출 ${fmtEok(p.spend)}${p.pension ? " · 연금 " + fmtEok(p.pension) : ""}</span>` : ""));
  });
  svg.addEventListener("mouseleave", () => { cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); hideTip(); });
  container.appendChild(svg);

  const lg = document.createElement("div"); lg.className = "sim-legend";
  lg.innerHTML = `<span><i style="background:var(--c-us)"></i>${mode === "nominal" ? "명목 순자산" : "실질 순자산(오늘 가치)"}</span>`
    + `<span><i style="background:var(--c-vi)"></i>은퇴 ${retireAge}세</span>`
    + (depAge ? `<span><i style="background:var(--neg)"></i>자산 소진 ${depAge}세</span>` : "")
    + (pts.some(p => p.cycle === "폭락")
        ? `<span><i style="background:var(--neg);opacity:.45"></i>폭락</span>`
          + `<span><i style="background:var(--pos);opacity:.35"></i>회복</span>` : "");
  container.appendChild(lg);
}

function renderSim(sim, net) {
  const sec = document.getElementById("sim-section");
  if (!sim || !sim.series || !sim.series.length) { if (sec) sec.style.display = "none"; return; }
  sec.style.display = "";
  // 출발점을 화면의 '지금' 순자산에 맞춘다. 시트의 '현재' 행은 ★월별자산을 읽어 만든
  // 그 달 값이라 라이브 평가액과 몇 백만원씩 어긋난다. 차트와 표가 같은 곳에서 출발해야
  // 위 KPI와도 한 시점이 된다 — 이후 연도는 시트의 예측을 그대로 쓴다(우리가 다시 굴리지 않는다).
  const series = sim.series.map(r => ({ ...r }));
  const nowRow = series.find(r => (r.phase || "").includes("현재"));
  const sheetNow = nowRow ? nowRow.net : null;
  if (nowRow && net > 0) { nowRow.net = net; nowRow.real_net = net; }
  const s = sim.summary || {};
  // FIRE 섹션과 나란히 놓이므로 큰 KPI 카드 대신 얇은 스탯 한 줄로 (소진 나이는 FIRE와도 겹침)
  const stat = (l, v) => `<span><em>${l}</em> <b>${v}</b></span>`;
  document.getElementById("sim-stats").innerHTML =
    stat("은퇴 시점 자산", `${fmtEok(s.retire_asset)} · ${sim.retire_age}세`) +
    stat("자산 소진", sim.depletion_age ? `${sim.depletion_age}세` : "없음") +
    stat("108세 실질", `<span class="${s.real_net_end < 0 ? "delta-down" : ""}">${fmtEok(s.real_net_end)}</span>`)
    + (s.cycle_on
        ? stat("경기순환", `<span class="delta-down">폭락 ${(s.crash_ages || []).slice(0, 4).join("·")}세…</span>`
            + (s.spend_cut > 0
                ? ` <span style="color:var(--pos)">생활비 −${s.spend_cut}%</span>` : ""))
        : "");

  // ── 연도별 표 헬퍼 — draw()가 paintTable을 부르므로 반드시 그보다 먼저 선언한다 ──
  const eok = v => (v / 1e8).toFixed(2) + "억";
  const man0 = v => v ? Math.round(v / 1e4).toLocaleString("ko-KR") : "–";
  document.getElementById("sim-fold-hint").textContent =
    `${series[0].age}~${series[series.length - 1].age}세 · ${series.length}개년`;

  let mode = "real";
  const draw = () => { simChart(document.getElementById("sim-chart"), series, mode, sim.retire_age, sim.depletion_age); paintTable(); };
  draw();
  document.getElementById("sim-seg").addEventListener("click", ev => {
    const b = ev.target.closest(".seg-btn"); if (!b) return;
    for (const x of document.querySelectorAll("#sim-seg .seg-btn")) x.classList.toggle("on", x === b);
    mode = b.dataset.mode; draw();
  });
  document.getElementById("sim-note").textContent =
    "소진 이후 구간은 표시에서 제외 · 실질 = 물가 반영 후 오늘 돈 가치"
    + (s.cycle_on
        ? " · 경기순환 반영 중 — 폭락·회복 주기는 ★종합 시트에서 직접 정합니다"
        : " · 경기순환 미반영 (★종합 시트에서 켤 수 있습니다)");

  // ── 연도별 표 (접힘) — 차트와 완전히 같은 series를 쓴다 ──────────────────

  function paintTable() {
    const primary = mode === "real" ? "real_net" : "net";
    const secondary = mode === "real" ? "net" : "real_net";
    const head = mode === "real"
      ? ["나이", "연도", "단계", "실질 순자산", "명목 순자산", "투자수익", "연지출", "의료비", "연금", "저축"]
      : ["나이", "연도", "단계", "명목 순자산", "실질 순자산", "투자수익", "연지출", "의료비", "연금", "저축"];
    document.getElementById("sim-table").innerHTML =
      `<thead><tr>${head.map(h => `<th>${h}</th>`).join("")}</tr></thead><tbody>`
      + series.map(r => {
        const isNow = (r.phase || "").includes("현재");
        const isRetire = r.age === sim.retire_age && !isNow;
        const isDep = r.age === sim.depletion_age;
        const cls = isNow ? "sim-now" : (isRetire || isDep) ? "sim-mark"
                  : (sim.depletion_age && r.age > sim.depletion_age) ? "sim-after" : "";
        const tag = isNow ? `<span class="sim-tag">지금</span>`
                  : isRetire ? `<span class="sim-tag">은퇴</span>`
                  : isDep ? `<span class="sim-tag">소진</span>`
                  : r.cycle === "폭락" ? `<span class="sim-tag crash">폭락</span>`
                  : r.cycle === "회복" ? `<span class="sim-tag rec">회복</span>` : "";
        const neg = v => v < 0 ? ` class="delta-down"` : "";
        return `<tr class="${cls}"><td>${r.age}세${tag}</td><td>${esc(r.year)}</td><td>${esc(r.phase)}</td>`
          + `<td${neg(r[primary])}>${eok(r[primary])}</td>`
          + `<td style="color:var(--ink-muted)">${eok(r[secondary])}</td>`
          + `<td${neg(r.invest)}>${man0(r.invest)}</td><td>${man0(r.spend)}</td>`
          + `<td>${man0(r.medical)}</td><td>${man0(r.pension)}</td><td>${man0(r.saving)}</td></tr>`;
      }).join("") + "</tbody>";
    const gap = sheetNow != null && net > 0 ? net - sheetNow : 0;
    document.getElementById("sim-table-note").innerHTML =
      "순자산은 억, 나머지는 만원 단위 · 출처는 시뮬레이션 시트이고 연도별 예측은 시트가 계산합니다."
      + ` 맨 윗줄 '지금'은 위 KPI·자산 배분과 같은 <b>${eok(net)}</b>으로 맞췄습니다`
      + (Math.abs(gap) >= 1e6
          ? ` (시트의 현재 행 ${eok(sheetNow)}과 ${gap > 0 ? "+" : "−"}${eok(Math.abs(gap))} 차이 — 시트는 월 단위 기록, 이쪽은 실시간 평가액입니다).`
          : ".")
      + (sim.depletion_age ? ` 소진(${sim.depletion_age}세) 이후 줄은 흐리게 뒀습니다 — 모델이 빚을 계속 굴리는 비현실 구간입니다.` : "");
  }
}

/* ---- 우리 부부 연간 리뷰 (연간리뷰) ---- */
/* 베스트 카드용 파스텔 스티키 팔레트 [배경, 카테고리 잉크] + 살짝 기운 각도 */
const RV_STICKY = [
  ["#FFE08A", "#7a5c00"], ["#FFC7D3", "#93334f"], ["#BDEACB", "#1f6e46"],
  ["#AAD6F6", "#1a5480"], ["#FFD3A8", "#8a5320"], ["#DAC6F3", "#553a8c"],
  ["#EAE79B", "#5e5c1a"], ["#A9E7E1", "#1a6a63"], ["#FBBFA6", "#94401f"],
];
const RV_ROT = [-2.4, 1.7, -1.3, 2.1, -1.9, 1.2, -2.2, 1.5];

function renderReview(rv) {
  const tabBtn = document.querySelector('.tab[data-tab="review"]');
  if (!rv || !rv.years || !rv.years.length) { if (tabBtn) tabBtn.style.display = "none"; return; }
  const seg = document.getElementById("review-years");
  seg.innerHTML = rv.years.map(y => `<button class="seg-btn" data-y="${y}">${y}</button>`).join("");

  const draw = year => {
    const d = rv.byYear[String(year)] || { best: [], months: [] };
    for (const b of seg.querySelectorAll(".seg-btn")) b.classList.toggle("on", b.dataset.y == year);
    document.getElementById("review-best-h2").textContent = `${year} 베스트`;
    const bestCard = document.getElementById("review-best-card");
    bestCard.style.display = d.best.length ? "" : "none";
    document.getElementById("review-best").innerHTML = d.best.map((b, i) => {
      const [bg, ink] = RV_STICKY[i % RV_STICKY.length];
      const rot = RV_ROT[i % RV_ROT.length];
      return `<div class="rv-card" style="background:${bg};--note-ink:${ink};--rot:${rot}deg">
        <div class="rv-cat">${esc(b.label)}</div><div class="rv-txt">${esc(b.text)}</div></div>`;
    }).join("");
    const mCard = document.getElementById("review-months-card");
    mCard.style.display = d.months.length ? "" : "none";
    document.getElementById("review-months").innerHTML = d.months.map(m =>
      `<div class="rv-month"><div class="rv-m">${esc(m.label)}</div><div class="rv-mtxt">${esc(m.text)}</div></div>`).join("");
  };
  seg.addEventListener("click", ev => {
    const b = ev.target.closest(".seg-btn"); if (!b) return;
    draw(+b.dataset.y);
  });
  // 기본 선택 — 베스트가 채워진 가장 최근 연도 (진행 중이라 빈 올해는 건너뜀)
  const rich = rv.years.find(y => (rv.byYear[String(y)]?.best || []).length >= 3);
  draw(rich || rv.years[0]);
}

function initTabs() {
  const nav = document.getElementById("tabs");
  nav.style.display = "flex";
  if (_tabsInited) return;   // 재렌더(업데이트 버튼) 시 리스너 중복 방지
  _tabsInited = true;

  // 넘치는 쪽 가장자리만 흐리게 — 스크롤바를 숨겼으니 이게 유일한 '더 있다' 신호다
  const syncFade = () => {
    const max = nav.scrollWidth - nav.clientWidth;
    nav.classList.toggle("fade-l", nav.scrollLeft > 1);
    nav.classList.toggle("fade-r", nav.scrollLeft < max - 1);
  };
  nav.addEventListener("scroll", syncFade, { passive: true });
  addEventListener("resize", syncFade);
  syncFade();
  nav.addEventListener("click", ev => {
    const b = ev.target.closest(".tab");
    if (!b) return;
    if (b.classList.contains("on")) return;      // 같은 탭 다시 눌러 깜빡이지 않게
    for (const t of nav.querySelectorAll(".tab")) {
      const on = t === b;
      t.classList.toggle("on", on);
      // 시각 상태만 바꾸면 스크린리더는 어느 탭이 열렸는지 알 수 없다
      t.setAttribute("aria-selected", on ? "true" : "false");
    }
    // 탭 목록을 여기 하드코딩하면 탭을 늘릴 때마다 이 배열을 같이 고쳐야 하고, 잊으면
    // 버튼은 눌리는데 내용이 안 뜬다 ('다음 후보집'을 넣을 때 실제로 그랬다).
    // 버튼에서 직접 읽어 두 곳이 어긋날 여지를 없앤다.
    for (const id of [...nav.querySelectorAll(".tab")].map(t => t.dataset.tab)) {
      const el = document.getElementById("tab-" + id);
      if (!el) continue;
      const show = b.dataset.tab === id;
      el.setAttribute("role", "tabpanel");
      el.setAttribute("aria-hidden", show ? "false" : "true");
      el.style.display = show ? "" : "none";
      if (show) {
        // 애니메이션을 매번 다시 태우려면 클래스를 뗐다가 리플로우 후 붙여야 한다
        el.classList.remove("tab-panel-in");
        void el.offsetWidth;
        el.classList.add("tab-panel-in");
        revealIn(el);                            // 새 탭 안의 카드도 순서대로 떠오르게
      }
    }
    // 좁은 화면에서 반쯤 잘린 탭을 눌렀을 때 그 탭이 온전히 보이게 끌어온다
    b.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
    syncFade();
    // 탭을 바꾸면 그 탭의 처음부터 읽는 게 자연스럽다 (이미 위에 있으면 건드리지 않는다)
    if (window.scrollY > 120) window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

