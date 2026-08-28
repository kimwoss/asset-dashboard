/* ---- 스크롤 진입 연출 -------------------------------------------------------
   화면에 들어오는 카드를 한 번만 떠오르게 한다. IntersectionObserver라 스크롤마다
   계산하지 않아 부드럽고, 한 번 본 카드는 관찰을 끊어 되돌아와도 다시 움직이지 않는다.
   움직임 최소화를 켠 사용자에겐 아예 걸지 않는다(CSS에서도 한 번 더 막는다). */
let _revealObs = null;
const _show = el => { el.classList.add("seen"); if (_revealObs) _revealObs.unobserve(el); };

function revealIn(root) {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (!("IntersectionObserver" in window)) return;
  if (!_revealObs) {
    _revealObs = new IntersectionObserver((entries, obs) => {
      for (const e of entries) if (e.isIntersecting) _show(e.target);
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.06 });
  }
  const scope = root || document;
  const inView = el => {
    const r = el.getBoundingClientRect();
    return r.height > 0 && r.top < innerHeight && r.bottom > 0;
  };
  [...scope.querySelectorAll("section.card, .cards")].forEach((el, i) => {
    if (el.classList.contains("seen") || el.classList.contains("reveal")) return;
    // 숨은 요소(display:none)에는 아예 걸지 않는다 — 높이가 0이라 영영 '보였다'가 안 되고
    // opacity:0만 남아, 나중에 그 섹션이 켜져도 투명한 채로 남는다.
    if (el.offsetParent === null && getComputedStyle(el).position !== "fixed") return;
    el.classList.add("reveal");
    el.style.transitionDelay = `${Math.min(i, 6) * 45}ms`;
    // 이미 화면에 걸쳐 있으면 관찰을 기다리지 않고 바로 띄운다. 관찰자 콜백은 다음 프레임
    // 이후에나 오는데, 그동안 첫 화면이 비어 보이는 게 연출보다 나쁘다.
    if (inView(el)) { requestAnimationFrame(() => _show(el)); return; }
    _revealObs.observe(el);
  });
  // 최후 안전장치 — 어떤 이유로든 관찰이 안 돌면 연출을 포기하고 내용을 드러낸다.
  // 애니메이션이 콘텐츠를 영영 가리는 일만은 없어야 한다.
  clearTimeout(revealIn._t);
  revealIn._t = setTimeout(() => {
    for (const el of document.querySelectorAll(".reveal:not(.seen)"))
      if (inView(el)) _show(el);
  }, 900);
}

/* ---- 복호화 (scripts/crypto_util.py와 동일 포맷) ---- */
const b64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));

async function decryptEnvelope(envText, passphrase) {
  const o = JSON.parse(envText);
  const raw = await crypto.subtle.importKey("raw", new TextEncoder().encode(passphrase), "PBKDF2", false, ["deriveKey"]);
  const key = await crypto.subtle.deriveKey(
    { name: "PBKDF2", salt: b64(o.salt), iterations: o.iter || 600000, hash: "SHA-256" },
    raw, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
  const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv: b64(o.iv) }, key, b64(o.ct));
  return new TextDecoder().decode(pt);
}

/* ---- 실시간 시세 (live-data 브랜치) ----
   크론은 30분 간격으로 걸어두었지만 GitHub이 실제로 주는 주기는 중앙값 100분이다
   (실측 2026-07: 48시간 26회 = 기대 96회의 27%, 최대 공백 251분).
   그래서 '30분마다'라고 약속하지 않고, 화면에는 배지로 실제 기준시각을 밝힌다.
   raw.githubusercontent.com은 CORS 허용 + 5분 캐시. 실패해도 무시하고 스냅샷을 쓴다. */
const LIVE_URL = "https://raw.githubusercontent.com/kimwoss/asset-dashboard/live-data/live.enc";

async function loadLive(passphrase) {
  try {
    const r = await fetch(LIVE_URL + "?t=" + Date.now());  // 매 호출 캐시 우회 (업데이트 버튼 대응)
    if (!r.ok) return null;
    return JSON.parse(await decryptEnvelope(await r.text(), passphrase));
  } catch (e) {
    console.warn("실시간 시세 실패 — 스냅샷 사용", e);
    return null;
  }
}

/* 스냅샷 위에 실시간 시세를 덮어쓴다. 뉴스·운세·부동산·배당은 그대로 둔다
   (자주 안 바뀌고, 30분마다 재생성하면 AI 쿼터만 축낸다). */
function applyLive(snap, live) {
  if (!live) return null;
  // 체크포인트(인사말·날씨·운세)를 30분 잡이 읽어온 최신본으로 교체 — 모닝 리포트가 이른
  // 아침 시트에 올리면 무거운 일별 잡(07:30)을 기다리지 않고 30분 내 반영된다.
  // 단, 일별 스냅샷이 더 최신이면(경계 시각) 밀어내지 않는다.
  if (live.checkpoint && live.checkpoint.generated_at) {
    const cur = snap.checkpoint && snap.checkpoint.generated_at;
    if (!cur || live.checkpoint.generated_at >= cur) snap.checkpoint = live.checkpoint;
  }
  if (snap.checkpoint) {
    let applied = false;
    for (const k of ["us", "kr", "fx"])
      if (live[k] && live[k].length) { snap.checkpoint[k] = live[k]; applied = true; }
    // 뉴스도 실시간(30분)으로 덮어쓴다 — 07:00 모닝 뉴스가 온종일 옛것으로 남던 문제 해결
    if (live.news && live.news.length) { snap.checkpoint.news = live.news; snap.checkpoint.news_live = true; }
    // 실시간 시세가 실제로 붙었을 때만 기준시각을 남긴다 → 체크포인트가 '실시간' 배지를 켠다
    if (applied) snap.checkpoint.live_at = live.updated_at || null;
  }
  if (live.fx_usdkrw) snap.fx_usdkrw = live.fx_usdkrw;

  // 구글시트에서 끌어오는 블록을 30분 최신본으로 교체 — 사용자가 시트를 고치면 최대 30분 내,
  // '업데이트하기'로는 즉시 반영된다 (서버 live 잡이 시트를 읽어 발행). 없으면 일별 스냅샷 유지.
  // 은퇴 생활비(spending.retire)는 일별 잡만 싣는다 — live.spending로 덮이면 사라지므로 보존한다.
  const baseRetire = snap.spending && snap.spending.retire;
  // prev_* (전일·전월·전년 기준)도 30분 잡이 싣는다 — 종전엔 일별 스냅샷에만 있어
  // 달이 바뀐 날 아침(일별 잡 전)에 '전월'이 지지난달을 가리켰다.
  for (const k of ["financial", "fire", "monthly", "asset_history", "liabilities",
                   "spending", "cities", "officetel", "simulation", "review", "annual_flow",
                   "prev_day", "prev_month", "prev_year"])
    if (live[k]) snap[k] = live[k];
  if (snap.spending && !snap.spending.retire && baseRetire) snap.spending.retire = baseRetire;

  // 계좌 평가액 — live.financial로 이미 최신 holdings가 왔으면 그대로. 못 받았을 때만 옛 스케일 폴백.
  if (!live.financial && live.accounts && snap.financial && snap.financial.holdings) {
    const cur = {};
    for (const h of snap.financial.holdings) { const k = `${h.owner}|${h.account}`; cur[k] = (cur[k] || 0) + h.value_krw; }
    for (const h of snap.financial.holdings) {
      const k = `${h.owner}|${h.account}`;
      if (live.accounts[k] != null && cur[k] > 0) h.value_krw = Math.round(h.value_krw * (live.accounts[k] / cur[k]));
    }
  }

  // 자산 현황의 '주식'을 투자 포트폴리오(★주식계좌)와 같은 값으로 재연계 — 두 탭 액수 일치를
  // 구조적으로 보장한다. live.financial이 왔든, 못 와서 위에서 accounts로 스케일만 했든,
  // 아무것도 못 받아 스냅샷 그대로든 — 최종 snap.financial.holdings 하나만 보고 맞춘다.
  // (예전엔 live.financial이 있을 때만 맞춰서, 스케일 폴백 경로에서 두 탭이 어긋났다.)
  if (snap.financial && snap.financial.holdings && Array.isArray(snap.assets)) {
    const own = {};
    for (const h of snap.financial.holdings) own[h.owner] = (own[h.owner] || 0) + h.value_krw;
    for (const a of snap.assets)
      if (a.category === "주식" && own[a.owner] != null) a.value_krw = own[a.owner];
  }

  // 자산·부채가 갱신됐으면 총자산·총부채·순자산 재계산 (KPI·합계·도넛 반영).
  if (Array.isArray(snap.assets)) {
    snap.gross_krw = snap.assets.reduce((s, a) => s + (a.value_krw || 0), 0);
    if (live.liabilities && live.liabilities.length)
      snap.debt_krw = live.liabilities.reduce((s, l) => s + (l.amount_krw || 0), 0);
    if (snap.debt_krw != null) { snap.net_krw = snap.gross_krw - snap.debt_krw; snap.total_krw = snap.net_krw; }
  }

  return live.updated_at || null;
}

async function loadData(passphrase) {
  const bust = "?t=" + Date.now();
  const [encSnap, encHist] = await Promise.all([
    fetch("data/latest.enc" + bust).then(r => { if (!r.ok) throw new Error("latest.enc HTTP " + r.status); return r.text(); }),
    fetch("data/history.enc" + bust).then(r => r.ok ? r.text() : ""),
  ]);
  const snap = JSON.parse(await decryptEnvelope(encSnap, passphrase));
  const histText = encHist ? await decryptEnvelope(encHist, passphrase) : "";
  return [snap, histText];
}

// 인트로를 부드럽게 걷어낸다 — render()가 끝난 뒤 호출해 빈 화면 깜빡임을 없앤다.
function dismissIntro() {
  const intro = document.getElementById("intro");
  if (!intro) return;
  intro.classList.add("out");
  setTimeout(() => intro.remove(), 1100);
}

// 시네마틱 인트로 겸 게이트. 데이터가 준비되면 resolve하되 인트로는 유지 —
// main()이 render() 후 dismissIntro()로 걷어내 완성된 대시보드가 곧바로 드러난다.
async function gate() {
  const pwRow = document.getElementById("introPw"), autoRow = document.getElementById("introAuto");
  const input = document.getElementById("pw"), btn = document.getElementById("pwbtn"),
        msg = document.getElementById("pwmsg");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  // 인트로 연출을 끝까지 보여줄 최소 시간 (재방문 자동진입도 이 시간은 머문다)
  const minShow = new Promise(r => setTimeout(r, reduce ? 300 : 2400));

  const saved = localStorage.getItem("asset_pw");
  if (saved) {
    autoRow.style.display = "";
    try {
      const [data] = await Promise.all([loadData(saved), minShow]);
      return data;
    } catch {
      localStorage.removeItem("asset_pw");
      autoRow.style.display = "none";
    }
  }

  // 신규 방문 또는 저장된 비밀번호 실패 — 비밀번호 입력
  pwRow.style.display = "";
  setTimeout(() => input.focus(), reduce ? 350 : 1750);
  return new Promise(resolve => {
    const attempt = async () => {
      const pw = input.value;
      if (!pw) return;
      btn.disabled = true; msg.textContent = "확인 중…";
      try {
        const data = await loadData(pw);
        localStorage.setItem("asset_pw", pw);
        resolve(data);
      } catch (e) {
        btn.disabled = false;
        msg.textContent = String(e).includes("HTTP")
          ? "데이터를 불러오지 못했어요 (" + e + ")"
          : "비밀번호가 맞지 않아요.";
      }
    };
    btn.addEventListener("click", attempt);
    input.addEventListener("keydown", ev => { if (ev.key === "Enter") attempt(); });
  });
}

// 게이트에서 받은 원본 스냅샷·이력은 그대로 보관하고, 렌더할 때마다 복제본에 실시간을
// 덧입힌다 — '업데이트하기'가 여러 번 눌려도 원본이 오염(누적 스케일 등)되지 않는다.
let baseSnap = null, histText = "";

function showToast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.classList.add("on");
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => t.classList.remove("on"), 2200);
}

// 업데이트 트리 — 화면의 숫자는 반드시 이 순서로만 내려온다.
//   ① 구글시트(★월별자산·★가계부·★주식계좌 등)  = 사람이 쓰는 원장
//   ② 일별 잡 07:30 KST → latest.enc / history.enc = 그날의 확정 스냅샷
//   ③ 30분 잡 → live.enc                          = 시세·보유·부채 실시간 덮어쓰기
//   ④ applyLive(snap, live)                       = ②에 ③을 통째로 갈아끼움
//   ⑤ 아래 net / gross / debt                     = '지금'을 뜻하는 단 하나의 값
//   ⑥ KPI · 자산 배분 도넛 · FIRE · 후보 도시 · 순자산 추이 끝점이 전부 ⑤만 참조
// ⑤를 건너뛰고 위젯이 ②를 직접 읽으면 한 화면에 시점이 두 개 생긴다 — 금지.
async function render() {
  const snap = structuredClone(baseSnap);

  // 실시간 시세·뉴스·체크포인트 덮어쓰기 (10분 갱신). 실패하면 스냅샷 그대로 — 화면은 항상 뜬다.
  // live를 이름 있는 변수로 받는다 — 아래 신선도 배지가 _fetched를 들여다봐야 한다.
  const live = await loadLive(localStorage.getItem("asset_pw"));
  const liveAt = applyLive(snap, live);

  // 등급별로 무엇이 언제 값인지 한 번에 알려 준다. 대시보드에서 가장 자주 나오는
  // 물음이 "이거 지금 값이야?"인데, 지금까지는 답할 방법이 없었다.
  function freshnessTip(live) {
    const t = (iso) => {
      if (!iso) return "—";
      const d = new Date(iso);
      if (isNaN(d)) return "—";
      const m = Math.max(0, Math.round((Date.now() - d) / 60000));
      return m < 1 ? "방금" : m < 60 ? m + "분 전" : Math.round(m / 60) + "시간 전";
    };
    const f = (live && live._fetched) || {};
    const q = (live && live.financial && live.financial.quotes_asof) || null;
    return [
      "T1 실시간 (10분 목표)",
      `  주식·환율  ${t(q)}` + (q ? "  ← 가격을 직접 조회" : ""),
      `  계좌 평가액 ${t(f.financial)}`,
      "T2 반나절 (3시간)",
      `  가계부·목표·시뮬  ${t(f.spending)}`,
      "T3·T4",
      `  다음 후보집 ${t(f.officetel)} · 도시 ${t(f.cities)}`,
      "부동산 KB시세는 주 1회(금) 일별 잡이 맡습니다.",
    ].join("\n");
  }

  // 헤더 메타 — 종전엔 시세·스냅샷·환율이 같은 크기 회색 글씨로 나열돼, 무엇이 '지금'
  // 값인지 판단이 안 됐다. 실시간 여부는 점 있는 배지로 올리고(가장 먼저 눈에 걸림),
  // 스냅샷 시각은 보조로 내린다. 환율은 데이터라 시세 영역에서 따로 보여준다.
  const hdr = document.getElementById("updated");
  if (liveAt) {
    // 몇 분 전인지까지 적는다. 시각만 있으면 '지금 값인가'를 사람이 매번 계산해야 한다.
    // 배지 색은 나이로 바꾼다 — 10분 이내가 목표이고, 넘어가면 눈에 걸려야 한다.
    const mins = (() => {
      const m = liveAt.match(/(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})/);
      if (!m) return null;
      return Math.max(0, Math.round(
        (Date.now() - new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5])) / 60000));
    })();
    const stale = mins != null && mins > 20;   // 10분 주기 + 한 번 걸러도 20분 안에는 온다
    const ago = mins == null ? "" : mins < 1 ? " · 방금" : ` · ${mins}분 전`;
    hdr.innerHTML = `<span class="hdr-live${stale ? " stale" : ""}" title="${
        esc(freshnessTip(live))}"><span class="dot"></span>실시간 ${
        liveAt.replace(" KST", "")}${ago}</span>`
                  + `<span class="hdr-snap">스냅샷 ${(snap.updated_at || "").replace(" KST", "")}</span>`;
  } else {
    // 실시간을 못 받았다는 사실을 화면에 남긴다. 종전엔 '스냅샷'만 떠서, 기기마다 순자산이
    // 다르게 보여도 왜 그런지 단서가 없었다 — 폰만 실시간을 못 받으면 반나절 전 값이
    // 조용히 표시된다(2026-08 문의). live.enc는 raw.githubusercontent 한 곳에서만 오므로
    // 그 호스트가 막힌 망에서는 이 배지가 켜진다.
    const why = live ? "" :
      `<span class="hdr-live stale" title="실시간 파일(live.enc)을 받지 못했습니다. 아래 값은 일별 스냅샷 기준입니다. 망에서 raw.githubusercontent.com이 막혀 있으면 이 상태가 됩니다."><span class="dot"></span>실시간 못 받음</span>`;
    hdr.innerHTML = why + `<span class="hdr-snap">스냅샷 ${(snap.updated_at || "").replace(" KST", "")}</span>`;
  }
  document.getElementById("fx").textContent = snap.fx_usdkrw
    ? "환율 " + Number(snap.fx_usdkrw).toLocaleString() + "원/$" + (liveAt ? "" : " (" + snap.fx_asof + ")")
    : "";

  // ── '지금' 값 (단일 기준) ─────────────────────────────────────────────
  // 화면에 현재로 찍히는 순자산·총자산·부채는 전부 여기서만 나온다. applyLive가
  // 끝난 직후 한 번 확정하고 KPI·도넛·FIRE·후보 도시·추이 끝점이 모두 이걸 참조한다.
  // 예전엔 KPI/도넛은 라이브, 추이는 history.csv(그날 아침 스냅샷)를 따로 읽어서
  // 같은 화면에 순자산이 18.28억과 18.23억으로 동시에 떴다 (2026-08-04).
  const todayKST = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
  const net = snap.net_krw ?? snap.total_krw;
  const gross = snap.gross_krw ?? snap.assets.reduce((s, a) => s + a.value_krw, 0);
  const debt = snap.debt_krw ?? 0;

  renderHeroBand(snap, net);

  // history → 일별 순자산 (부채가 음수로 들어와 행 합계가 곧 순자산)
  const daily = new Map();
  for (const line of histText.trim().split("\n").slice(1)) {
    if (!line) continue;
    const cols = line.split(",");
    const date = cols[0], v = Number(cols[cols.length - 1]);
    daily.set(date, (daily.get(date) || 0) + v);
  }
  const hist = [...daily.entries()].sort((a, b) => a[0] < b[0] ? -1 : 1)
    .map(([date, total]) => ({ date, total }));

  // 추이 차트용 — 월별 1점(그 달 마지막 값)으로 집계.
  // history.csv는 실행할 때마다 그날 행이 쌓여 이번 달만 일별로 촘촘해진다.
  // 그대로 그리면 시간이 갈수록 x축이 뭉개지므로 월 단위로 접는다 (KPI 델타는 daily 유지).
  const byMonth = new Map();
  for (const p of hist) byMonth.set(p.date.slice(0, 7), { ...p });
  // 이번 달 점은 위에서 확정한 '지금' 순자산으로 덮는다 — 이력 파일의 오늘 행은
  // 일별 잡이 아침에 기록한 값이라, 그대로 두면 도넛과 추이가 서로 다른 시점을 말한다.
  const curKey = todayKST.slice(0, 7);
  byMonth.set(curKey, { date: todayKST, total: net });
  const histM = [...byMonth.values()].sort((a, b) => a.date < b.date ? -1 : 1);

  // 연 단위 보기 — 각 해의 마지막 점 하나. 올해는 '지금' 값이 그 해의 끝점이 된다.
  // 기본을 이쪽으로 두는 이유: 지난 해들은 어차피 연말 1점뿐이라, 올해만 월별로 촘촘하면
  // x축의 한 칸이 어떤 해는 1년이고 어떤 해는 1달이라 기울기를 눈으로 비교할 수 없다.
  const byYear = new Map();
  for (const p of histM) byYear.set(p.date.slice(0, 4), p);
  const histY = [...byYear.values()];

  // KPI
  // 전일·전월·전년 대비 (%). 색은 방향이 아니라 '우리에게 좋은가'로 — 부채는 줄면 초록.
  // 전월=지금이면 6월말, 전년=2025년말 기준. 기준값이 없는 항목은 조용히 생략한다.
  const pm = snap.prev_month;
  const bases = [["전일", snap.prev_day], ["전월", snap.prev_month], ["전년", snap.prev_year]];
  // ── 증감의 기준시점: 기준점만 과거에 고정, 현재값은 언제나 '지금' ──────────
  // 증감 = 지금(실시간) − 기준 시점의 확정치. 주식 앱이 '전일 종가 대비 현재가'를
  // 보여주는 것과 같은 읽기다. 값은 장중에 계속 움직이는 게 맞다 — 그게 이 화면의 쓸모다.
  //
  // 한때 '오늘 확정 vs 전일 확정'으로 바꿔 하루 종일 고정시킨 적이 있는데(2026-08-20),
  // 큰 숫자(지금)와 증감(확정)이 서로 다른 시점을 말하게 되어 기준이 둘로 갈렸다.
  // 기준은 하나여야 한다 — 현재값은 항상 지금, 비교 대상만 이름 붙은 과거 시점.
  // 그 과거 시점이 무엇인지는 아래 kpi-note가 못박는다.
  const subDeltas = (field, cur, goodWhenDown) => {
    const parts = bases.map(([lb, b]) => {
      const base = b && b[field];
      if (!base) return "";
      const d = cur - base, pct = d / base * 100, good = goodWhenDown ? d <= 0 : d >= 0;
      return `<span class="kd"><i>${lb}</i> <b class="${good ? "delta-up" : "delta-down"}">`
           + `${d >= 0 ? "▲" : "▼"}${Math.abs(pct).toFixed(1)}%</b></span>`;
    }).filter(Boolean);
    return parts.length ? `<span class="kpi-deltas">${parts.join("")}</span>` : "";
  };

  // 순자산 hero 카드. FIRE 진행 게이지는 바로 아래 'FIRE 목표 달성' 카드가 같은 것을
  // 더 자세히 보여줘서 뺐다 — 같은 숫자를 두 번 읽게 하면 어느 쪽이 진짜인지 헷갈린다.
  let cards = `<div class="card hero"><div class="label">순자산 <span class="asof">${liveAt ? "지금 " + liveAt.slice(11, 16) : "스냅샷"}</span></div>
    <div class="value">${eokMan(net)}</div>
    <div class="sub">${subDeltas("net_krw", net, false) || "총자산 − 부채"}</div></div>`;
  cards += kpiCard("총자산", eokMan(gross), subDeltas("gross_krw", gross, false) || "부채 제외 전");
  if (debt) cards += kpiCard("부채", "−" + eokMan(debt), subDeltas("debt_krw", debt, true) || "대출·상환 예정");
  // 올해 저축률 — 자산 3종이 '쌓인 결과'라면 이건 '쌓이는 속도'다. 같은 줄에 둔다.
  const flow = annualFlow(snap.annual_flow);
  const cur = flow[0];
  if (cur) {
    cards += kpiCard(`${cur.year}년 저축률`, cur.savingsRate.toFixed(1) + "%",
      `순잉여 ${eokMan(cur.surplus)} · ${cur.months}개월 누계`);
  }
  document.getElementById("kpis").innerHTML = cards;
  // 기준값이 어디서 왔는지 밝힌다 — 시트 소계는 부동산을 추정으로 굴려 우리 실시간
  // 평가액과 계통 차이가 있다. 일별 기록이 한 달을 채우면 자동으로 실측 비교로 바뀐다.
  // 기준시점을 화면에 못박는다 — 이 한 줄이 '이 숫자가 언제 것인가'의 유일한 답이다.
  const pd = snap.prev_day;
  document.getElementById("kpi-note").innerHTML =
    `증감은 <b>지금${liveAt ? " " + liveAt.slice(11, 16) : ""}</b> 값을 아래 시점의 확정치와 비교합니다 — `
    + [
        pd && `<b>전일</b> ${pd.key} 07:30`,
        pm && `<b>전월</b> ${pm.key} 말${pm.source === "sheet" ? "(★월별자산 소계·부동산 추정가)" : ""}`,
        snap.prev_year && `<b>전년</b> ${snap.prev_year.key} 말`,
      ].filter(Boolean).join(" · ")
    + `. 확정치는 매일 아침 07:30에 한 번 찍으며, 직전 미국장 마감 직후라 그 시점에 하루가 닫힙니다.`;

  // FIRE 목표 달성 (★종합 시트) — 달성률은 위 실시간 net으로 재계산
  renderFire(snap.fire, net);
  renderAnnualFlow(snap.annual_flow);

  // ---- 자산 구성 도넛 3종 ----
  const A = snap.assets, L = snap.liabilities || [];
  const sumV = arr => arr.reduce((s, x) => s + x.value_krw, 0);
  const sumL = arr => arr.reduce((s, x) => s + x.amount_krw, 0);
  const inCat = c => A.filter(a => a.category === c);
  const re = sumV(inCat("부동산"));
  const stockUH = sumV(A.filter(a => a.category === "주식" && a.owner === "우현"));
  const stockGR = sumV(A.filter(a => a.category === "주식" && a.owner === "규리"));
  const jeonse = sumV(inCat("전세보증금"));
  const cash = sumV(inCat("현금"));
  const rentalDep = sumL(L.filter(l => l.kind === "rental_deposit"));
  const loan = sumL(L.filter(l => l.kind === "loan"));
  const C = { re: "var(--c-re)", uh: "var(--c-us)", gr: "var(--c-vi)", jeonse: "var(--c-kr)", cash: "var(--c-cash)", debt: "var(--c-debt)" };

  // 순자산 배분 — 부채를 '그 부채가 산 자산'에 상계해 순지분만 남긴다.
  // 순자산은 이미 부채를 뺀 결과이므로 대출을 조각으로 넣으면 범주 오류가 된다
  // (구버전: 분모가 절대값 합이라 중앙 순자산값과 링 100%가 어긋났음).
  const debtFor = t => sumL(L.filter(l => (l.target || "무담보") === t));
  const reNet = re - debtFor("부동산");            // 부동산 − (임대보증금 + 주택담보)
  const jeonseNet = jeonse - debtFor("전세보증금"); // 거주 전세 − 전세대출
  const unsecured = debtFor("무담보");             // 담보 없는 대출 → 자산 비중대로 안분
  const equity = [
    { label: "부동산 순지분", value: reNet, color: C.re },
    { label: "주식", value: stockUH + stockGR, color: C.uh },
    { label: "전세 순지분", value: jeonseNet, color: C.jeonse },
    { label: "현금", value: cash, color: C.cash },
  ];
  const equitySum = equity.reduce((s, x) => s + x.value, 0);
  const k = equitySum > 0 ? (equitySum - unsecured) / equitySum : 0;  // 안분 후 합 = 순자산
  const netSlices = equity.map(s => ({ ...s, value: s.value * k }));

  const dc = document.getElementById("donuts");
  dc.innerHTML = "";
  donut(donutCell(dc), {
    title: "총자산 배분", caption: "부채 차감 전", center: gross, centerLabel: "총자산",
    slices: [
      { label: "부동산", value: re, color: C.re },
      { label: "우현 주식", value: stockUH, color: C.uh },
      { label: "규리 주식", value: stockGR, color: C.gr },
      { label: "전세보증금", value: jeonse, color: C.jeonse },
      { label: "현금", value: cash, color: C.cash },
    ],
  });
  donut(donutCell(dc), {
    title: "순자산 배분", caption: "대출을 담보 자산에 상계한 순지분", center: net, centerLabel: "순자산",
    slices: netSlices,
  });
  document.getElementById("donut-note").textContent =
    `대출을 담보 자산에 상계한 순지분 기준` +
    (unsecured > 0 ? ` · 무담보 ${fmtEok(unsecured)}은 자산 비중대로 안분` : "");

  // 추이 — 마지막 점은 위 KPI·도넛과 같은 '지금' 값이다 (아래 안내로 명시).
  // 기본은 연 단위. 올해만 월별로 촘촘하면 x축 한 칸의 뜻이 해마다 달라져
  // 기울기를 눈으로 비교할 수 없다. 올해 안을 보고 싶으면 차트를 눌러 펼친다.
  const asof = liveAt ? `${liveAt} 실시간 평가액` : `${snap.updated_at} 스냅샷`;
  const curY = curKey.slice(0, 4), curM = Number(curKey.slice(5));
  let trendYearly = true;
  const drawTrend = () => {
    const box = document.getElementById("trend");
    lineChart(box, trendYearly ? histY : histM, { yearly: trendYearly });
    box.style.cursor = "pointer";
    box.title = trendYearly ? `${curY}년 월별로 펼치기` : "연 단위로 접기";
    document.getElementById("trend-note").textContent = trendYearly
      ? `해마다 1점 — ${curY}년은 ${asof} 기준으로, 위 KPI·자산 배분과 같은 시점입니다.`
        + ` 차트를 누르면 ${curY}년을 월별로 펼칩니다.`
      : `2025년까지는 연말 기준 · 2026년부터는 월말 기준 · ${curY}년 ${curM}월은 ${asof}`
        + ` — 위 KPI·자산 배분과 같은 시점입니다. 차트를 누르면 연 단위로 접힙니다.`;
  };
  document.getElementById("trend").addEventListener("click", () => {
    trendYearly = !trendYearly;
    drawTrend();
  });
  drawTrend();

  // 금융자산 탭 (★주식계좌)
  initTabs();
  renderFinancial(snap.financial);
  renderMonthly(snap.monthly);
  renderSpending(snap.spending, snap.liabilities);
  renderCashflow(snap.financial, snap.fire);   // 건보료·목표구성은 은퇴 시점 세팅(CF_OWN_*)+FIRE 목표 기준
  renderCities(snap.cities, net);
  renderOfficetel(snap.officetel);
  renderSim(snap.simulation, net);
  renderReview(snap.review);
  // 브리핑 맨 위 금융자산 — 현재값은 실시간, 전일은 history, 전월·전년은 asset_history
  renderCheckpoint(snap.checkpoint,
    finTodayHtml(snap.financial, finDailyByOwner(histText, todayKST), snap.asset_history));

  // 상세 테이블 (자산 + 부채) — 비고 대신 전월·전년 대비 증감
  const H = snap.asset_history || {};
  const hAssets = H.assets || {}, hLiab = H.liabilities || {};
  // 자산 상세 라인 → ★월별자산 이력 키 매칭
  const histFor = (name, category, owner) => {
    if (category === "주식") return hAssets["계좌:" + owner];
    if (category === "부동산") return Object.entries(hAssets).find(([k]) => name.includes(k))?.[1];
    if (category === "전세보증금") return Object.entries(hAssets).find(([k]) => k.includes("전세"))?.[1];
    // 이름이 곧 이력 키인 항목 (회사주식·외화). 없으면 null — 현금성 자산 등은 이력이 없다.
    return hAssets[name] || null;
  };
  // ⚠️ 증감의 '현재값'은 반드시 이 표에 찍은 평가액(라이브)을 쓴다.
  //    예전엔 asset_history.cur(=일별 잡이 ★월별자산에 얼려 둔 값)을 썼는데, 평가액 열은
  //    30분마다 갱신되는 라이브라 둘의 기준이 어긋났다. 2026-08-04 실측: 우현 주식계좌가
  //    평가액 4.08억(라이브)인데 전월 대비는 스냅샷(4.04억) 기준 +119만으로 찍혀,
  //    표의 4.08억 − 전월 4.03억 = 478만과 맞지 않았다. 합계 행은 라이브 기준이라
  //    개별 행을 다 더해도 합계 증감과 어긋났다. 기준을 평가액으로 통일한다.
  // 증감 셀: base(전월/전년값) 대비 cur의 변화. goodWhenUp=false면 감소가 초록(부채).
  // 억/만원 혼합 — 대출 상환 등 소액도 '33만'처럼 보이게 (fmtEok만 쓰면 0.00억).
  const fmtChg = v => Math.abs(v) >= 1e8 ? fmtEok(v) : fmtMan(v);
  const deltaCell = (cur, base, goodWhenUp = true) => {
    if (base == null || !base) return `<td class="delta-none">—</td>`;
    const d = cur - base, pct = d / Math.abs(base) * 100;
    if (Math.abs(d) < 5e4) return `<td class="delta-none">–</td>`;  // 5만 미만 무변동
    const good = goodWhenUp ? d > 0 : d < 0;
    return `<td class="${good ? "delta-up" : "delta-down"}">${d > 0 ? "▲" : "▼"} ${fmtChg(Math.abs(d))}`
         + `<br><small>${d > 0 ? "+" : "−"}${Math.abs(pct).toFixed(1)}%</small></td>`;
  };

  const rows = [...snap.assets].sort((a, b) => b.value_krw - a.value_krw).map(a => {
    const h = histFor(a.name, a.category, a.owner) || {};
    return `<tr>
      <td class="name"><span class="chip" style="background:${CAT_COLORS[a.category] || "var(--baseline)"}"></span>${a.name}</td>
      <td>${a.owner}</td><td>${a.category}</td>
      <td><b>${fmtEok(a.value_krw)}</b></td>
      ${deltaCell(a.value_krw, h.m1, true)}
      ${deltaCell(a.value_krw, h.y1, true)}
    </tr>`;
  }).join("");
  const debtRows = (snap.liabilities || []).map(l => {
    const h = hLiab[l.name] || {};
    return `<tr>
      <td class="name"><span class="chip" style="background:var(--down)"></span>${l.name}</td>
      <td>${l.owner}</td><td>부채</td>
      <td class="delta-down"><b>−${fmtEok(l.amount_krw)}</b></td>
      ${deltaCell(l.amount_krw, h.m1, false)}
      ${deltaCell(l.amount_krw, h.y1, false)}
    </tr>`;
  }).join("");
  // 합계 행 — 총자산은 자산 행 끝, 총부채는 부채 행 끝, 순자산은 맨 아래.
  // 현재값은 KPI와 동일한 snap, 전월/전년 기준은 ★월별자산 소계(25·37·38행).
  const T = H.totals || {};
  const sumRow = (label, cur, base, goodWhenUp, cls) => `<tr class="sum-row">
    <td class="name" colspan="3"><b>${label}</b></td>
    <td class="${cls || ""}"><b>${cls === "delta-down" ? "−" : ""}${fmtEok(Math.abs(cur))}</b></td>
    ${deltaCell(cur, base && base.m1, goodWhenUp)}
    ${deltaCell(cur, base && base.y1, goodWhenUp)}
  </tr>`;
  const grossRow = gross != null ? sumRow("총자산", gross, T.gross, true) : "";
  const debtSumRow = gross != null ? sumRow("총부채", debt, T.debt, false, "delta-down") : "";
  const netRow = gross != null ? sumRow("순자산", net, T.net, true, "sum-net") : "";

  const hpm = H.prev_month ? H.prev_month.replace("-", ".") : "전월";
  document.getElementById("detail").innerHTML = `
    <thead><tr><th>항목</th><th>소유</th><th>분류</th><th>평가액</th><th>${hpm} 대비</th><th>${H.prev_year || "전년"} 대비</th></tr></thead>
    <tbody>${rows}${grossRow}${debtRows}${debtSumRow}${netRow}</tbody>`;

  // 렌더가 끝난 뒤 보이는 탭의 카드에 스크롤 진입 연출을 건다 (숨은 탭은 열릴 때 건다)
  revealIn(document.querySelector('[id^="tab-"]:not([style*="display: none"])'));

  return liveAt ? `시세 ${liveAt} 기준` : `${snap.updated_at} 기준`;
}

/* 라이트/다크 수동 토글 — 버튼 아이콘은 현재 테마를 보여준다. SVG 차트는 CSS 변수를
   fill로 쓰므로 data-theme만 바꾸면 자동으로 다시 칠해진다(재렌더 불필요). */
function initTheme() {
  const btn = document.getElementById("theme");
  const eff = () => document.documentElement.dataset.theme
    || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const paint = () => { btn.textContent = eff() === "dark" ? "🌙" : "☀️"; };
  paint();
  btn.addEventListener("click", () => {
    const next = eff() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("theme", next);
    paint();
  });
}
initTheme();

async function main() {
  try {
    [baseSnap, histText] = await gate();
  } catch (e) {
    dismissIntro();
    const err = document.getElementById("err");
    err.style.display = "block";
    err.textContent = "데이터를 불러오지 못했습니다. 로컬에서 열었다면 `python -m http.server`로 docs 폴더를 서빙해서 보세요. (" + e + ")";
    return;
  }
  // 렌더가 던져도 인트로는 반드시 걷는다. 종전에는 render()가 예외를 내면
  // dismissIntro()에 닿지도 못해 화면이 영원히 인트로에 갇혔다 — 위젯 하나가
  // 죽었을 뿐인데 대시보드 전체를 못 보는 건 너무 비싼 대가다.
  // (2026-08-23 신선도 배지가 없는 변수를 참조해 실제로 이렇게 갇혔다)
  try {
    await render();
  } catch (e) {
    console.error("render 실패", e);
    const err = document.getElementById("err");
    if (err) {
      err.style.display = "block";
      err.textContent = "일부 화면을 그리지 못했습니다 — 나머지는 아래에 그대로 있습니다. (" + e + ")";
    }
  } finally {
    dismissIntro();  // 렌더 완료(또는 실패) 후 인트로 걷어내기
  }

  // 업데이트하기 — 브라우저가 할 수 있는 최대: 발행된 최신본을 모두 다시 받아 재렌더.
  //   · latest.enc + history (일별 자산·부동산·FIRE·생활비·이력) ← loadData
  //   · live.enc (실시간 시세·뉴스·체크포인트, 30분 갱신) ← render 안 loadLive
  // 정적 사이트라 시세·뉴스를 브라우저가 직접 긁는 건 불가(야후·구글 CORS 차단) — 서버(CI)가
  // 발행한 값을 캐시 우회해 즉시 당겨온다. CI가 갱신했으면 숫자가 실제로 바뀌어 보인다.
  const rb = document.getElementById("refresh");
  rb.style.display = "";

  // 마지막으로 데이터를 받아 온 시각. 화면에 다시 돌아왔을 때 다시 받을지 판단한다.
  let lastLoad = Date.now();

  const refreshAll = async (silent) => {
    if (rb.disabled) return;
    rb.disabled = true; rb.classList.add("spin");
    const t0 = Date.now();
    try {
      const pw = localStorage.getItem("asset_pw");
      [baseSnap, histText] = await loadData(pw);   // 일별 발행본 재수신 (핵심 — 종전엔 live만 받았다)
      const freshness = await render();            // live.enc 재수신 + 전체 재렌더
      lastLoad = Date.now();
      // 자동 갱신은 조용히 한다 — 앱을 오갈 때마다 토스트가 뜨면 성가시다.
      if (!silent) { flashUpdated(); showToast(`업데이트 완료 · ${freshness}`); }
    } catch (e) {
      // 자동 갱신이 실패하면 화면을 건드리지 않고 그대로 둔다(기존 값이 남는 편이 빈 화면보다 낫다)
      if (!silent) showToast("업데이트 실패 — 잠시 후 다시 시도해 주세요");
    } finally {
      // 스핀이 너무 짧게 깜빡이지 않도록 최소 600ms 유지 (동작했다는 체감)
      setTimeout(() => { rb.disabled = false; rb.classList.remove("spin"); }, Math.max(0, 600 - (Date.now() - t0)));
    }
  };
  rb.addEventListener("click", () => refreshAll(false));

  // 화면에 다시 돌아오면 알아서 최신화한다.
  //
  // 종전엔 페이지를 처음 열 때 딱 한 번 그리고 끝이었다. 폰은 탭을 켜 둔 채로 두는 일이
  // 흔해서, 며칠 전에 받은 화면이 그대로 남아 있었다 — 데스크톱과 폰이 서로 다른 시각의
  // 순자산을 보여준 원인이다(2026-08 제보). latest.enc(일별)와 live.enc(10분)는 최대
  // 반나절 넘게 벌어지기도 한다.
  //
  // pageshow(persisted)도 함께 듣는다. bfcache로 복원되면 스크립트가 다시 돌지 않고
  // visibilitychange도 오지 않는 경우가 있다(iOS Safari에서 흔하다).
  const AUTO_REFRESH_GAP = 60_000;   // 잠깐 다른 앱에 다녀오는 정도로는 다시 받지 않는다
  const maybeAutoRefresh = () => {
    if (document.visibilityState !== "visible") return;
    if (Date.now() - lastLoad < AUTO_REFRESH_GAP) return;
    refreshAll(true);
  };
  // visibilitychange는 document에서 발생한다. window에 걸면 버블링에 기대게 되므로
  // 표준 대상인 document에 직접 건다.
  document.addEventListener("visibilitychange", maybeAutoRefresh);
  addEventListener("pageshow", e => { if (e.persisted) maybeAutoRefresh(); });
}

// 업데이트 직후 헤더 시각과 현재 탭에 짧은 하이라이트 — '방금 갱신됐다'는 시각적 신호
function flashUpdated() {
  const up = document.getElementById("updated");
  if (up) { up.classList.remove("flash-in"); void up.offsetWidth; up.classList.add("flash-in"); }
  const active = document.querySelector('#tabs .tab.on');
  const pane = active && document.getElementById("tab-" + active.dataset.tab);
  if (pane) { pane.classList.remove("flash-in"); void pane.offsetWidth; pane.classList.add("flash-in"); }
}
main();
