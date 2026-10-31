/* Market moves of today's holdings. Deposits and withdrawals are not investment returns. */
const ACCOUNT_HORIZONS = [["d1", "1일 전"], ["w1", "1주 전"], ["m1", "1개월 전"], ["y1", "1년 전"]];

function accountMovesHtml(fin) {
  const data = fin?.account_performance;
  const rows = data?.accounts || [];
  const money = n => Number(n).toLocaleString("ko-KR", {maximumFractionDigits: 0}) + "원";
  const cell = (period, horizon) => {
    if (!Number.isFinite(period?.pct) || !Number.isFinite(period?.delta_krw)) {
      return '<td class="account-unavailable" title="비교 시세가 없거나 일부 종목의 조회에 실패했습니다">—</td>';
    }
    const sign = period.delta_krw > 0 ? "+" : period.delta_krw < 0 ? "−" : "";
    const direction = Math.abs(period.pct) < 0.005 ? "flat" : period.pct > 0 ? "rise" : "fall";
    const dates = (period.base_dates || []).join(", ");
    return `<td title="${esc(dates ? '비교 종가일: ' + dates : '시세 비대상 자산')}"><span class="${horizon === 'd1' ? 'delta-chip ' + direction : 'account-' + direction}">${period.pct > 0 ? '+' : ''}${period.pct.toFixed(2)}%</span><small class="account-amount ${'account-' + direction}">${sign}${money(Math.abs(period.delta_krw))}</small></td>`;
  };
  const owners = [...new Set(rows.map(row => row.owner))];
  const body = owners.map(owner => `<tr class="mkt-grp"><td colspan="6">${esc(owner)}</td></tr>` + rows.filter(row => row.owner === owner).map(row => `<tr><td>${esc(row.account)}</td><td class="mkt-px">${money(row.current_krw)}</td>${ACCOUNT_HORIZONS.map(([key]) => cell(row.periods?.[key], key)).join('')}</tr>`).join('')).join('');
  return `<div class="cp-mkt-head"><h2 id="account-moves-title">계좌별 시세 증감</h2>${data?.asof ? `<span class="live-badge off">${esc(data.asof.slice(0,16).replace('T',' '))} 기준</span>` : ''}</div>
    <p class="cp-mkt-note">현재 보유 수량 기준 · 해외주식 환율 반영 · 배당·입출금 제외</p>
    ${rows.length ? `<div class="tbl-scroll"><table class="mkt mkt-unified account-moves"><thead><tr><th scope="col">계좌</th><th scope="col">현재 평가액</th>${ACCOUNT_HORIZONS.map(([, label]) => `<th scope="col">${label}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table></div>` : '<p class="cp-mkt-note">계좌별 비교 시세를 준비 중입니다. 다음 데이터 갱신 후 표시됩니다.</p>'}
    <p class="cp-mkt-note">각 기간 이전의 마지막 거래일 종가와 비교한 증감액·등락률입니다. 과거 실제 계좌 잔고·수익률과는 다릅니다. 현금·예금 평가액은 고정하며, 조회할 수 없는 기간은 —로 표시합니다.</p>`;
}

function renderAccountMoves(fin) {
  const panel = document.getElementById("account-moves");
  if (panel) panel.innerHTML = accountMovesHtml(fin);
}

if (typeof module !== "undefined" && module.exports) module.exports = {accountMovesHtml};
