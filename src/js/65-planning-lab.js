/* A transparent, deterministic planning aid, separate from the sheet projection. */
function projectSavings(start, monthly, annualPercent, months) {
  if (![start, monthly, annualPercent, months].every(Number.isFinite) || start < 0 || monthly < 0 || annualPercent <= -100 || months < 0 || months > 1200) return null;
  const rate = Math.pow(1 + annualPercent / 100, 1 / 12) - 1;
  if (Math.abs(rate) < 1e-12) return start + monthly * months;
  const factor = Math.pow(1 + rate, months);
  return start * factor + monthly * (factor - 1) / rate;
}
function renderPlanningLab(snap) {
  const host = document.getElementById("planning-lab");
  if (!host) return;
  const holdings = snap.financial?.holdings || [];
  const liquid = holdings.filter(h => h.group === "유동성").reduce((s, h) => s + (Number(h.value_krw) || 0), 0);
  const pension = holdings.filter(h => h.group === "연금성").reduce((s, h) => s + (Number(h.value_krw) || 0), 0);
  const today = kstDay();
  const f = snap.fire || {};
  const targetMonths = f.target_year ? (f.target_year - Number(today.slice(0, 4))) * 12 + (f.target_month || 12) - Number(today.slice(5, 7)) : 24;
  const defaults = { months: Math.min(360, Math.max(1, targetMonths)), saving: 0, rate: 3, expense: Math.round((f.monthly_expense || 5000000) / 10000) };
  const values = renderPlanningLab.values || defaults;
  const field = (id, label, value, min, max, step, unit) => '<label for="plan-' + id + '">' + label + '<span><input type="number" id="plan-' + id + '" name="' + id + '" value="' + value + '" min="' + min + '" max="' + max + '" step="' + step + '" inputmode="decimal" required><em>' + unit + '</em></span></label>';
  host.innerHTML = '<div class="lab-header"><div><span class="eyebrow">WHAT IF, TOGETHER</span><h2>우리의 선택을 바꿔보면.</h2><p>월 저축과 수익률을 바꿔 투자자산의 준비 정도를 비교해 보세요.</p></div><span class="lab-tag">가정 기반 계산</span></div>' +
    '<form id="planning-form" class="planning-form">' +
    field("months","준비 기간",values.months,1,360,1,"개월") +
    field("saving","월 추가저축",values.saving,0,100000,1,"만원") +
    field("rate","연 수익률 가정",values.rate,-50,50,.1,"%") +
    field("expense","은퇴 후 월 지출",values.expense,1,100000,1,"만원") +
    '<button type="submit">다시 계산하기 ↗</button></form><div id="planning-output" aria-live="polite"></div>' +
    '<p class="lab-note">실시간 투자 평가액을 출발점으로, 매월 말 저축·고정 수익률을 가정합니다. 추가저축은 유동성 계좌에만 반영합니다. 부동산·부채·세금·수수료·배당의 별도 현금 유출입은 계산하지 않으며, 시트 원본은 바뀌지 않습니다. 생활비 충당기간은 은퇴 후 수익·소득 없이 같은 금액을 쓰는 단순 계산입니다.</p>';
  function draw() {
    const form = document.getElementById("planning-form");
    if (!form.reportValidity()) return;
    const get = key => Number(form.elements.namedItem(key).value);
    const v = { months: get("months"), saving: get("saving"), rate: get("rate"), expense: get("expense") };
    renderPlanningLab.values = v;
    const lv = projectSavings(liquid, v.saving * 10000, v.rate, v.months);
    const pv = projectSavings(pension, 0, v.rate, v.months);
    const out = document.getElementById("planning-output");
    if (!holdings.length) { out.textContent = "계산에 필요한 투자 보유내역이 없습니다."; return; }
    if (lv == null || pv == null) { out.textContent = "가정값을 다시 확인해 주세요."; return; }
    out.innerHTML = '<div class="lab-results"><div><span>준비 기간 후 유동성 투자자산</span><strong>' + eokMan(lv) + '</strong><small>현재 ' + eokMan(liquid) + ' + 저축·가정 수익</small></div><div><span>연금성 투자자산 · 별도</span><strong>' + eokMan(pv) + '</strong><small>인출 시기·조건은 계좌별로 다름</small></div><div><span>유동성 자산의 생활비 충당기간</span><strong>' + (lv / (v.expense * 10000) / 12).toFixed(1) + '년</strong><small>월 ' + v.expense.toLocaleString("ko-KR") + '만원 지출 가정</small></div></div>' +
      '<div class="lab-comparison">' + [0, 3, 5].map(rate => '<span>연 ' + rate + '% 가정 <b>' + fmtEok(projectSavings(liquid, v.saving * 10000, rate, v.months)) + '</b></span>').join("") + '</div>';
  }
  document.getElementById("planning-form").onsubmit = ev => { ev.preventDefault(); draw(); };
  draw();
}
if (typeof module !== "undefined" && module.exports) module.exports = { projectSavings };
