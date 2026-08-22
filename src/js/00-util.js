
const CAT_COLORS = {
  "부동산":     "var(--c-re)",
  "주식":       "var(--c-us)",
  "전세보증금": "var(--c-kr)",
  "현금":       "var(--c-cash)",
  "미국주식":   "var(--c-us)",
  "한국주식":   "var(--c-kr)",
  "기타":       "var(--baseline)",
};
const CATS = ["부동산", "주식", "전세보증금", "현금"];
const fmtEok = v => (v / 1e8).toLocaleString("ko-KR", { maximumFractionDigits: 2 }) + "억";
const fmtWon = v => Math.round(v).toLocaleString("ko-KR") + "원";
// "18억 7324만원" 형식 (억+만원). 부호는 호출부에서 붙인다(절대값 기준).
const eokMan = v => {
  const a = Math.round(Math.abs(v)), e = Math.floor(a / 1e8), m = Math.round((a - e * 1e8) / 1e4);
  if (e && m) return `${e}억 ${m}만원`;
  if (e) return `${e}억`;
  return `${m.toLocaleString("ko-KR")}만원`;
};
const tooltip = document.getElementById("tooltip");

// 터치 기기 판별 — 마우스가 없으면 mouseleave가 영원히 오지 않는다.
const _coarsePointer = matchMedia("(hover: none), (pointer: coarse)").matches;
let _tipTimer = null;

function showTip(ev, html) {
  tooltip.innerHTML = html;
  tooltip.style.display = "block";
  const pad = 14;
  let x = ev.clientX + pad, y = ev.clientY + pad;
  const r = tooltip.getBoundingClientRect();
  if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - pad;
  if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - pad;
  tooltip.style.left = x + "px"; tooltip.style.top = y + "px";
  // 터치에는 '커서가 떠났다'는 신호가 없어 툴팁이 영영 남는다. 스스로 사라지게 한다.
  clearTimeout(_tipTimer);
  // 4초 — 세 줄짜리 툴팁(나이·순자산·지출/연금)을 읽을 만큼은 두되 잊히지 않을 만큼만.
  // 스크롤·다른 곳 터치가 주된 해제 수단이고 이건 '두고 자리를 뜬' 경우의 안전망이다.
  if (_coarsePointer) _tipTimer = setTimeout(hideTip, 4000);
}
function hideTip() { clearTimeout(_tipTimer); tooltip.style.display = "none"; }

// 툴팁은 position:fixed라 스크롤해도 화면에 붙어 따라온다. 모바일에선 mouseleave가
// 없어 한 번 뜨면 지워지지 않았다(2026-08 제보). 화면이 움직이거나 다른 곳을 건드리면
// 무조건 걷어낸다 — 차트를 다시 만지면 mousemove가 곧바로 새로 띄운다.
// capture:true — 안쪽 스크롤 컨테이너의 scroll은 위로 버블링되지 않는다.
addEventListener("scroll", hideTip, { passive: true, capture: true });
addEventListener("touchstart", hideTip, { passive: true });
addEventListener("resize", hideTip);
addEventListener("orientationchange", hideTip);

function el(tag, attrs = {}, parent) {
  const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}

