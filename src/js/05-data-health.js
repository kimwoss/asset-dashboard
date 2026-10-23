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
const HEALTH_BLOCKS = [
  ["financial", "투자 평가액", 22, "시세 조회·시트 보유수량 기준"],
  ["news", "관심 뉴스", 30, "기사 발행 시각은 원문에서 확인"],
  ["checkpoint", "오늘의 브리핑", 1500, "아침 리포트 생성 기준"],
  ["spending", "생활비", 75, "시트 수집 기준 · 입력 마감과 다름"],
  ["fire", "은퇴 목표", 75, "시트 수집 기준 · 계획값"],
  ["simulation", "은퇴 전망", 75, "시트 계산 기준 · 예측값"],
  ["liabilities", "부채", 75, "시트 수집 기준"],
  ["officetel", "후보집", 135, "시트 수집 기준 · 매물 확인일은 별도"],
  ["cities", "후보 도시", 375, "시트 수집 기준 · 현지 조사일은 별도"],
];
function dataHealth(snap, live, now = Date.now()) {
  const published = live?.updated_iso || live?.updated_at;
  const publicationAge = dataAge(published, now);
  const blocks = HEALTH_BLOCKS.map(([key, label, limit, note]) => {
    const meta = live?._status?.[key];
    const available = live && Object.hasOwn(live, key) && live[key] != null;
    const time = key === "checkpoint" ? (live?.checkpoint?.generated_at || snap.checkpoint?.generated_at) : live?._fetched?.[key];
    const age = dataAge(time, now);
    const state = meta?.state === "error" ? "error" : !available ? "snapshot" : age == null ? "unknown" : age > limit ? "stale" : "ok";
    return { key, label, time, age, state, note, sourceTime: key === "financial" ? live?.financial?.quotes_asof : null };
  });
  const warnings = blocks.filter(b => b.state !== "ok");
  return { published, publicationAge, blocks, warnings,
    state: !live ? "snapshot" : publicationAge == null || publicationAge > 22 || warnings.length ? "attention" : "ok" };
}
function presentValue(object, key) { return object != null && Object.hasOwn(object, key) && object[key] != null; }
if (typeof module !== "undefined" && module.exports)
  module.exports = { dataTime, dataAge, ageLabel, kstDay, dataHealth, presentValue };
