/**
 * 분당부부 대시보드 — live.yml 10분 트리거 (Google Apps Script)
 *
 * 왜 필요한가
 *   워크플로에 크론을 걸어 두었지만 GitHub의 schedule 이벤트는 공개 레포에서
 *   best-effort다. 실측(2026-07-28) 48시간 26회 = 기대 96회의 27%, 간격 중앙값 100분,
 *   최대 공백 251분. 크론을 아무리 촘촘히 걸어도 GitHub이 주는 만큼만 돈다.
 *   그래서 밖에서 정확히 10분마다 workflow_dispatch로 깨운다.
 *   10분인 이유 — 주식 시세가 10분 넘게 어긋나면 '지금 값'이라 부를 수 없다.
 *   Apps Script 시간 트리거는 1·5·10·15·30분만 되고, 실행당 1초 남짓이라
 *   하루 144회를 써도 소비자 계정 한도(트리거 총 90분/일)의 3%다.
 *
 * 왜 Apps Script인가
 *   이미 쓰는 구글 계정이라 새 서비스 가입이 없고, 시간 기반 트리거가 무료다.
 *   하루 48회 호출은 UrlFetch 할당량(2만/일)에 견줘 무시할 수준이다.
 *   워크플로의 schedule 크론은 지우지 않는다 — 이 트리거가 죽어도 100분마다는 돈다(폴백).
 *
 * 설치 (토큰은 본인만 다룰 것 — 코드에 절대 적지 말 것)
 *   1) GitHub → Settings → Developer settings → Personal access tokens
 *      → Fine-grained tokens → Generate new token
 *        · Repository access: Only select repositories → kimwoss/asset-dashboard
 *        · Permissions → Repository permissions → Actions: Read and write
 *        · Expiration: 원하는 만료일 (만료되면 갱신 필요)
 *   2) script.google.com → 새 프로젝트 → 이 파일 내용 붙여넣기
 *   3) 프로젝트 설정(⚙) → 스크립트 속성 → 속성 추가
 *        이름 GITHUB_TOKEN / 값 = 1)에서 받은 토큰
 *      ※ 스크립트 속성에 두면 코드·공유 링크에 토큰이 노출되지 않는다.
 *   4) 함수 목록에서 triggerLive 실행 → 권한 승인 → GitHub Actions 탭에
 *      "update-live-quotes" 실행이 workflow_dispatch로 뜨는지 확인
 *   5) 함수 목록에서 setUpTrigger 실행 → 10분 트리거 등록 완료
 *      ※ 주기를 바꿨으면 반드시 setUpTrigger를 다시 실행해야 한다.
 *        기존 트리거는 지워지고 새 주기로 다시 걸린다.
 *
 * 장 시간에만 10분 (2026-10 개편)
 *   트리거는 여전히 10분마다 깨어나지만, 장이 닫힌 시간엔 30분에 한 번만 디스패치한다.
 *     · 한국장  평일 08:50–15:50 KST
 *     · 미국장  평일 09:20–16:20 뉴욕 시각 (서머타임은 뉴욕 시계로 자동 추종)
 *     · 그 밖   30분 간격 — 시트에서 고친 생활비·자산은 30분 안에 반영된다
 *   종전엔 주말·새벽에도 하루 144회 돌았다. 시장이 닫혀 있으면 바뀌는 게 없는데도
 *   시트 API를 읽고 live-data 브랜치를 다시 썼다. 주당 ~1,000회 → ~620회.
 *   간격 판단은 '마지막 디스패치 후 경과 시간'으로 한다 — 트리거가 몇 분 흔들려도
 *   30분에 정확히 한 번이 유지된다.
 *
 * 해제
 *   removeTrigger 실행. (워크플로의 schedule 크론은 그대로 남아 폴백으로 동작)
 */

const REPO = "kimwoss/asset-dashboard";
const WORKFLOW = "live.yml";
const REF = "main";
const OFF_HOURS_GAP_MIN = 30;   // 장이 닫힌 시간의 디스패치 간격

/** 지금 한국장이나 미국장이 열려 있나 (앞뒤 여유 10~20분 포함). */
function marketOpen(now) {
  const kst = Utilities.formatDate(now, "Asia/Seoul", "u H m").split(" ").map(Number);
  const ny  = Utilities.formatDate(now, "America/New_York", "u H m").split(" ").map(Number);
  const kr = kst[0] <= 5 && inRange(kst[1] * 60 + kst[2], 8 * 60 + 50, 15 * 60 + 50);
  const us = ny[0] <= 5 && inRange(ny[1] * 60 + ny[2], 9 * 60 + 20, 16 * 60 + 20);
  return kr || us;
}
function inRange(m, lo, hi) { return m >= lo && m <= hi; }

/** 10분마다 불린다. 장중이면 매번, 아니면 30분에 한 번만 디스패치. */
function tick() {
  const now = new Date();
  const props = PropertiesService.getScriptProperties();
  const last = Number(props.getProperty("LAST_LIVE_MS") || 0);
  const gapMin = (now.getTime() - last) / 60000;
  if (!marketOpen(now) && gapMin < OFF_HOURS_GAP_MIN - 2) {   // -2: 트리거 흔들림 여유
    console.log(`장 마감 시간 — ${gapMin.toFixed(0)}분 전에 보냈으니 건너뜀`);
    return;
  }
  triggerLive();
  props.setProperty("LAST_LIVE_MS", String(now.getTime()));
}

/** live.yml 을 workflow_dispatch 로 깨운다. 성공하면 GitHub은 204를 준다(본문 없음). */
function triggerLive() {
  const token = PropertiesService.getScriptProperties().getProperty("GITHUB_TOKEN");
  if (!token) {
    throw new Error("스크립트 속성에 GITHUB_TOKEN이 없습니다 — 설치 3) 단계를 확인하세요.");
  }
  const url = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`;
  const res = UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    headers: {
      Authorization: "Bearer " + token,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    payload: JSON.stringify({ ref: REF }),
    muteHttpExceptions: true,   // 실패를 예외 대신 코드로 받아 로그에 남긴다
  });

  const code = res.getResponseCode();
  if (code === 204) {
    console.log(`OK — ${WORKFLOW} 실행 요청됨 (${new Date().toLocaleString("ko-KR")})`);
    return;
  }
  // 흔한 실패를 사람 말로 옮겨 준다 — 로그만 보고 원인을 알 수 있게
  const hint =
    code === 401 ? "토큰이 잘못됐거나 만료됨"
    : code === 403 ? "토큰 권한 부족 (Actions: Read and write 확인)"
    : code === 404 ? "레포/워크플로 경로가 틀렸거나 토큰이 이 레포에 접근 불가"
    : code === 422 ? `ref '${REF}' 가 없음`
    : "";
  console.error(`실패 ${code}${hint ? " — " + hint : ""}: ${res.getContentText()}`);
}

/** 10분 주기 트리거 등록 (기존 것은 지우고 새로 만든다 — 중복 등록 방지).
 *  깨우는 함수는 tick — 장 시간 판단을 거쳐 triggerLive를 부른다. */
function setUpTrigger() {
  removeTrigger();
  ScriptApp.newTrigger("tick").timeBased().everyMinutes(10).create();
  console.log("10분 트리거 등록 완료 — 장중 10분 · 그 외 30분 간격으로 깨웁니다.");
}

/** 트리거 해제. 워크플로의 schedule 크론은 그대로라 100분마다는 계속 돈다. */
function removeTrigger() {
  // 종전 버전(triggerLive 직접 호출)으로 걸린 트리거도 함께 지운다
  const gone = ScriptApp.getProjectTriggers()
    .filter((t) => ["tick", "triggerLive"].includes(t.getHandlerFunction()));
  gone.forEach((t) => ScriptApp.deleteTrigger(t));
  console.log(`기존 트리거 ${gone.length}개 해제`);
}
