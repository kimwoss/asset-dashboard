/* Premium dashboard shell. Every metric is derived from the existing snapshot. */
const JOURNEY_GROUPS = [
  { id: "today", label: "오늘", number: "01", tabs: ["checkpoint"] },
  { id: "money", label: "우리 돈", number: "02", tabs: ["overview", "financial", "spending"] },
  { id: "plan", label: "은퇴 계획", number: "03", tabs: ["retirement", "cashflow"] },
  { id: "life", label: "다음 삶", number: "04", tabs: ["officetel", "cities", "review"] },
];
let currentHealth = null;
function goDashboardTab(id) {
  const tab = document.querySelector('#tabs .tab[data-tab="' + id + '"]');
  if (tab && tab.style.display !== "none") tab.click();
}
function initJourney() {
  const shell = document.getElementById("journey-nav");
  shell.hidden = false;
  if (shell.dataset.ready) return;
  shell.dataset.ready = "1";
  shell.innerHTML = JOURNEY_GROUPS.map(g => '<button type="button" data-group="' + g.id + '" aria-pressed="false"><span>' + g.number + '</span>' + g.label + '</button>').join("");
  function selectGroup(id) {
    const group = JOURNEY_GROUPS.find(g => g.tabs.includes(id)) || JOURNEY_GROUPS[0];
    for (const b of shell.querySelectorAll("button")) b.setAttribute("aria-pressed", String(b.dataset.group === group.id));
    for (const t of document.querySelectorAll("#tabs .tab"))
      t.classList.toggle("out-of-group", !group.tabs.includes(t.dataset.tab));
    document.body.dataset.section = group.id;
  }
  document.getElementById("tabs").addEventListener("click", ev => {
    const b = ev.target.closest(".tab"); if (b) selectGroup(b.dataset.tab);
  }, true);
  shell.onclick = ev => {
    const b = ev.target.closest("[data-group]"); if (!b) return;
    const g = JOURNEY_GROUPS.find(x => x.id === b.dataset.group);
    const next = g.tabs.find(id => document.querySelector('#tabs .tab[data-tab="' + id + '"]')?.style.display !== "none");
    if (next) goDashboardTab(next);
    else showToast("이 영역의 데이터가 아직 없습니다.");
  };
  document.addEventListener("click", ev => {
    const b = ev.target.closest("[data-go-tab]");
    if (b) goDashboardTab(b.dataset.goTab);
  });
  selectGroup(document.querySelector("#tabs .tab.on")?.dataset.tab || "checkpoint");
}
function openHealth() {
  const dialog = document.getElementById("data-dialog");
  if (!dialog.open) dialog.showModal();
}
function renderDataHealth(snap, live) {
  currentHealth = dataHealth(snap, live);
  const h = currentHealth;
  const label = h.state === "snapshot" ? "일별 기록 표시 중" : h.state === "ok" ? "데이터 상태 확인" : "일부 데이터 확인 필요";
  const button = document.getElementById("data-status");
  button.hidden = false;
  button.dataset.state = h.state;
  button.innerHTML = '<span class="status-dot"></span><span>' + label + '</span><span aria-hidden="true">↗</span>';
  button.onclick = openHealth;
  const short = h.published ? "발행 " + ageLabel(h.published) : "일별 기록 기준";
  document.getElementById("updated").textContent = short;
  const labels = { ok: "정상", stale: "갱신 지연", error: "이전 값 유지", unknown: "시각 미제공", snapshot: "일별 기록" };
  document.getElementById("data-health-body").innerHTML =
    '<p class="health-intro">파일 발행과 원자료 기준은 다릅니다. 각 항목의 마지막 정상 수집과 현재 상태를 확인하세요.</p>' +
    '<div class="health-publication"><span>파일 발행</span><b>' + esc(h.published || snap.updated_at || "미제공") + '</b></div>' +
    h.blocks.map(b => '<div class="health-row"><div><b>' + b.label + '</b><small>' + esc(b.note) + '</small>' +
      (b.sourceTime ? '<small>가격 조회 ' + esc(ageLabel(b.sourceTime)) + ' · 거래 시각과 다를 수 있음</small>' : '') +
      '</div><div><span class="health-pill ' + b.state + '">' + labels[b.state] + '</span><small>' + esc(ageLabel(b.time)) + '</small></div></div>').join("") +
    '<p class="health-foot">부동산 KB시세는 주간 기준입니다. 가격 제공사의 지연, 휴장, 시트 입력 시점은 수집 주기와 별개입니다. 새로고침은 최신 발행본을 다시 불러옵니다.</p>';
  document.getElementById("data-close").onclick = () => document.getElementById("data-dialog").close();
  document.getElementById("data-dialog").onclick = ev => { if (ev.target === ev.currentTarget) ev.currentTarget.close(); };
}
function renderDailyOverview(snap, live, net) {
  const host = document.getElementById("daily-overview");
  const fin = snap.financial?.holdings || [];
  const liquid = fin.filter(h => h.group === "유동성").reduce((s, h) => s + (Number(h.value_krw) || 0), 0);
  const pension = fin.filter(h => h.group === "연금성").reduce((s, h) => s + (Number(h.value_krw) || 0), 0);
  const f = snap.fire || {};
  const target = Number(f.target_basic) || 0;
  const gap = target ? Math.max(0, target - net) : null;
  const delta = snap.prev_day?.net_krw != null ? net - snap.prev_day.net_krw : null;
  const of = snap.officetel?.items?.filter(x => x.ok) || [];
  const health = currentHealth;
  const kpi = (label, value, note, tab, extra = "") =>
    '<button type="button" class="daily-kpi ' + extra + '" data-go-tab="' + tab + '"><span>' + label + '</span><strong>' + value + '</strong><small>' + note + '</small><i aria-hidden="true">↗</i></button>';
  const today = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", month: "long", day: "numeric", weekday: "long" }).format(new Date());
  const actions = [];
  if (health?.warnings.length) actions.push({ label: "데이터 기준 확인", note: health.warnings.length + "개 항목의 수집 상태를 확인해 주세요.", health: true });
  if (gap != null) actions.push({ label: gap > 0 ? "은퇴 목표 점검" : "목표 달성 이후 계획", note: gap > 0 ? "기본 목표까지 " + eokMan(gap) + " 남았어요." : "현금흐름과 인출 계획을 함께 확인하세요.", tab: "retirement" });
  if (of.length) actions.push({ label: "다음 후보집 둘러보기", note: "기준 통과 " + of.length + "건 · 호가와 확인일을 비교해 보세요.", tab: "officetel" });
  else actions.push({ label: "은퇴 현금흐름 점검", note: "계획값과 실제 입금액을 구분해서 확인하세요.", tab: "cashflow" });
  host.innerHTML =
    '<div class="daily-heading"><div><span class="eyebrow">OUR NEXT CHAPTER</span><h2>오늘도, 우리의 속도로.</h2><p>' + today + ' · 우현과 규리의 경제적 자립 여정</p></div><span class="edition">DAILY<br>OVERVIEW</span></div>' +
    '<div class="daily-kpis">' +
    kpi("순자산 변화", delta == null ? "비교 기준 없음" : (delta < 0 ? "−" : "+") + eokMan(Math.abs(delta)), "직전 확정 기록 대비 · 수익률과 다름", "overview", delta < 0 ? "negative" : "") +
    kpi("유동성 투자자산", fin.length ? eokMan(liquid) : "데이터 없음", "연금성 제외 · 세금·출금 조건 별도", "financial") +
    kpi("연금성 투자자산", fin.length ? eokMan(pension) : "데이터 없음", "계좌 분류 기준 · 즉시 사용 가능액 아님", "financial") +
    kpi("기본 FIRE 진행", target ? (net / target * 100).toFixed(1) + "%" : "목표 미설정", target ? "목표 " + fmtEok(target) + " · 계획 기준" : "시트에 목표금액을 입력해 주세요", "retirement") +
    '</div><div class="daily-bottom"><div class="daily-note"><span class="eyebrow">A LITTLE CLOSER</span><h3>숫자 너머의 다음 일상.</h3><p>오늘의 변화는 차분하게,<br>다음 선택은 조금 더 선명하게.</p><button type="button" data-go-tab="cashflow">은퇴 계획 살펴보기 <span aria-hidden="true">↗</span></button></div>' +
    '<div class="daily-actions"><div class="section-caption"><h3>지금 살펴볼 것</h3><span>우선 확인할 세 가지</span></div>' +
    actions.slice(0, 3).map((a, i) => '<button type="button" ' + (a.health ? 'data-open-health' : 'data-go-tab="' + a.tab + '"') + '><span class="action-index">0' + (i + 1) + '</span><span><b>' + a.label + '</b><small>' + a.note + '</small></span><span aria-hidden="true">↗</span></button>').join("") + '</div></div>';
  host.querySelector("[data-open-health]")?.addEventListener("click", openHealth);
}
function renderHouseCards(of) {
  const host = document.getElementById("of-mobile-cards");
  if (!host) return;
  const listings = (of?.items || []).filter(x => x.ok).sort((a, b) => (a.converted || 0) - (b.converted || 0));
  if (!listings.length) { host.innerHTML = '<p class="empty-state">현재 기준을 통과한 매물이 없어요. 아래 타입 카탈로그를 확인해 주세요.</p>'; return; }
  host.innerHTML = listings.map(x => {
    const days = dataAge(x.asof);
    const terms = x.monthly ? Number(x.deposit).toLocaleString("ko-KR") + " / " + Number(x.monthly).toLocaleString("ko-KR") + "만원" : "전세 " + Number(x.deposit).toLocaleString("ko-KR") + "만원";
    const link = safeWebUrl(x.link);
    return '<article class="house-card"><div class="house-top"><span>' + esc(x.region || "후보집") + '</span><span class="' + (days == null || days > 14 * 1440 ? "house-old" : "") + '">' + esc(x.asof ? ageLabel(x.asof) + " 확인" : "확인일 미제공") + '</span></div><h3>' + esc(x.name) + '</h3><p>' + esc([x.type, x.area ? x.area.toFixed(2) + "평" : "", x.rooms].filter(Boolean).join(" · ")) + '</p><strong>' + terms + '</strong><dl><div><dt>환산전세</dt><dd>' + (x.converted == null ? "미제공" : (x.converted / 10000).toFixed(2) + "억") + '</dd></div><div><dt>층·향</dt><dd>' + esc([x.floor, x.facing].filter(Boolean).join(" · ") || "미제공") + '</dd></div></dl><div class="house-foot"><span>관리비·대출·전입 조건 별도 확인</span>' + (link ? '<a href="' + esc(link) + '" target="_blank" rel="noopener noreferrer">매물 보기 ↗</a>' : '<span>원문 링크 없음</span>') + '</div></article>';
  }).join("");
}
function safeWebUrl(value) {
  try { const u = new URL(value); return ["https:", "http:"].includes(u.protocol) ? u.href : ""; } catch { return ""; }
}
function renderExperience(snap, live, net) {
  initJourney();
  renderDataHealth(snap, live);
  renderDailyOverview(snap, live, net);
  renderHouseCards(snap.officetel);
  document.getElementById("lock-dashboard").hidden = false;
}
