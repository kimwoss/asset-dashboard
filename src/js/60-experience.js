let currentHealth = null;
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
  renderDataHealth(snap, live);
  renderHouseCards(snap.officetel);
  document.getElementById("lock-dashboard").hidden = false;
}
