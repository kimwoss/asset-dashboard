/* Poll publication quickly at opening boundaries. Source timestamps remain independent. */
function refreshGap(now = Date.now(), tab = "checkpoint") {
  const parts = zone => Object.fromEntries(new Intl.DateTimeFormat("en-US", {
    timeZone: zone, weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23"
  }).formatToParts(new Date(now)).filter(p => p.type !== "literal").map(p => [p.type, p.value]));
  const kr = parts("Asia/Seoul"), us = parts("America/New_York");
  const weekday = p => !["Sat", "Sun"].includes(p.weekday);
  const minute = p => Number(p.hour) * 60 + Number(p.minute);
  const active = (weekday(kr) && minute(kr) >= 540 && minute(kr) <= 940)
    || (weekday(us) && minute(us) >= 570 && minute(us) <= 970);
  const kbWindow = kr.weekday === "Fri" && minute(kr) >= 479 && minute(kr) < 570;
  return tab === "checkpoint" ? (active || kbWindow ? 30_000 : 60_000) : active || kbWindow ? 60_000 : 300_000;
}
if (typeof module !== "undefined" && module.exports) module.exports = { refreshGap };
