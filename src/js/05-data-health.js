/* Source time, publication time and retrieval are different clocks. */
function dataTime(value) {
  if (!value) return null;
  let text = String(value).trim().replace(/ KST$/, "+09:00");
  if (/^\d{4}-\d\d-\d\d$/.test(text)) text += "T00:00:00+09:00";
  else if (/^\d{4}-\d\d-\d\d[ T]\d\d:\d\d(?::\d\d)?$/.test(text)) text = text.replace(" ", "T") + "+09:00";
  else text = text.replace(/^(\d{4}-\d\d-\d\d) /, "$1T");
  const result = Date.parse(text);
  return Number.isFinite(result) ? result : null;
}
function dataAge(value, now = Date.now()) {
  const time = dataTime(value);
  return time == null ? null : Math.max(0, Math.floor((now - time) / 60000));
}
function ageLabel(value, now = Date.now()) {
  const age = dataAge(value, now);
  if (age == null) return "기준 시각 미제공";
  if (age < 1) return "방금";
  if (age < 60) return age + "분 전";
  if (age < 1440) return Math.floor(age / 60) + "시간 전";
  return Math.floor(age / 1440) + "일 전";
}
function kstDay(now = Date.now()) { return new Date(now + 9 * 3600e3).toISOString().slice(0, 10); }
function quoteSourceLabel(row) {
  const time = dataTime(row.price_at);
  const date = time == null ? (row.asof ? row.asof + " 가격 기준" : "가격 기준일 미제공")
    : new Date(time + 9 * 3600e3).toISOString().slice(0, 16).replace("T", " ") + " KST";
  return date + (row.price_kind === "intraday" ? " · 장중" : row.price_kind === "close" ? " · 종가" : "")
    + (row.source ? " · " + row.source : "")
    + (row.quote_state === "awaiting" ? " · 개장 후 시세 대기" : row.quote_state === "delayed" ? " · 시세 지연" : "");
}
const HEALTH_BLOCKS = [
  ["financial", "투자 평가액", 22, "시세 조회·시트 보유수량 기준"],
  ["market", "브리핑 시세", 8, "실제 거래 시각과 지연 여부는 종목별 표시"],
  ["real_estate", "KB 부동산", 90, "금요일 08시 이후 첫 수집부터 직접 조회 · 미갱신이면 재확인"],
  ["news", "관심 뉴스", 30, "기사 발행 시각은 원문에서 확인"],
  ["checkpoint", "오늘의 브리핑", 1500, "아침 리포트 생성 기준"],
  ["spending", "생활비", 75, "시트 수집 기준 · 입력 마감과 다름"],
  ["annual_flow", "연도별 소득·지출", 45, "연간 요약표를 매 발행마다 다시 조회"],
  ["fire", "은퇴 목표", 75, "시트 수집 기준 · 계획값"],
  ["simulation", "은퇴 전망", 75, "시트 계산 기준 · 예측값"],
  ["liabilities", "부채", 75, "시트 수집 기준"],
  ["officetel", "후보집", 135, "시트 수집 기준 · 매물 확인일은 별도"],
  ["cities", "후보 도시", 75, "시트 수집 기준 · 현지 조사일은 별도"],
];
function dataHealth(snap, live, now = Date.now()) {
  const published = live?.updated_iso || live?.updated_at;
  const publicationAge = dataAge(published, now);
  const blocks = HEALTH_BLOCKS.map(([key, label, limit, note]) => {
    const meta = live?._status?.[key];
    const available = live && Object.hasOwn(live, key) && live[key] != null;
    const time = key === "checkpoint"
      ? [snap.checkpoint?.generated_at, live?.checkpoint?.generated_at]
          .filter(value => dataTime(value) != null && dataTime(value) <= now)
          .sort((a, b) => dataTime(b) - dataTime(a))[0]
      : live?._fetched?.[key];
    const age = dataAge(time, now);
    const sourceError = (key === "cities" && !!live?.cities?.broken?.length) || (key === "real_estate" && !!live?.real_estate?.errors?.length);
    const pending = (key === "market" && (live?.market?.pending || live?.market?.delayed)) || (key === "real_estate" && live?.real_estate?.pending?.length);
    const state = meta?.state === "error" || sourceError ? "error" : !available ? "snapshot" : age == null ? "unknown" : (pending || age > limit || (key === "checkpoint" && kstDay(dataTime(time)) !== kstDay(now))) ? "stale" : "ok";
    const kbDate = (live?.real_estate?.assets || []).map(a => a.asof).filter(Boolean).sort()[0];
    return { key, label, time, age, state, note, sourceTime: key === "financial" ? live?.financial?.quotes_asof : key === "real_estate" ? kbDate : null,
      sourceLabel: key === "real_estate" ? "KB 시세 기준일" : "가격 조회" };
  });
  const warnings = blocks.filter(b => b.state !== "ok");
  return { published, publicationAge, blocks, warnings,
    state: !live ? "snapshot" : live._connection_error || publicationAge == null || publicationAge > 22 || warnings.length ? "attention" : "ok" };
}
function presentValue(object, key) { return object != null && Object.hasOwn(object, key) && object[key] != null; }
if (typeof module !== "undefined" && module.exports)
  module.exports = { dataTime, dataAge, ageLabel, kstDay, dataHealth, presentValue, quoteSourceLabel };
