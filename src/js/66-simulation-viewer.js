/* Read-only projections: the sheet remains the calculation source. */
function simulationYearFacts(row) {
  const value = key => Number.isFinite(row?.[key]) ? row[key] : null;
  const sum = (a,b) => value(a) == null || value(b) == null ? null : value(a) + value(b);
  return { nominal:value("net"), real:value("real_net"), expenses:sum("spend","medical"), income:sum("pension","retire_income") };
}
function renderSimulationViewer(sim, live) {
  const drawer = document.getElementById("simulation-drawer");
  if (!drawer) return;
  drawer.hidden = false;
  const toggleLabel = () => { document.getElementById("simulation-toggle-label").textContent = drawer.open ? "접기" : "펼쳐보기"; };
  toggleLabel();
  const source = document.getElementById("simulation-source-link");
  let sourceUrl = "";
  try { const u = new URL(sim?.source_url); if (u.protocol === "https:" && u.hostname === "docs.google.com" && u.pathname.startsWith("/spreadsheets/d/")) sourceUrl = u.href; } catch {}
  source.hidden = !sourceUrl;
  if (sourceUrl) source.href = sourceUrl; else source.removeAttribute("href");
  const series = sim?.series || [], hasData = series.length > 0;
  document.getElementById("simulation-empty").hidden = hasData;
  document.getElementById("simulation-year-view").hidden = !hasData;
  const fetched = live?._fetched?.simulation, state = live?._status?.simulation?.state;
  document.getElementById("simulation-asof").textContent = (fetched ? "수집 " + ageLabel(fetched) : "수집 시각 미제공")
    + (state === "error" ? " · 최근 수집 실패, 이전 기록" : !live?.simulation ? " · 일별 기록" : "");
  document.getElementById("simulation-preview").textContent = hasData
    ? (sim.retire_age != null ? "은퇴 " + sim.retire_age + "세 · " : "") + (sim.depletion_age != null ? "자산 소진 예상 " + sim.depletion_age + "세" : series[series.length-1].age + "세까지 소진 없음") + " · 시트 가정 기준"
    : "연동된 데이터가 아직 없습니다";
  if (!hasData) { drawer.ontoggle = toggleLabel; return; }
  const picker = document.getElementById("simulation-year"), previous = picker.value;
  picker.innerHTML = series.map((r,i)=>'<option value="'+i+'">'+esc(r.year || "")+' · '+r.age+'세 · '+esc(r.phase || "")+'</option>').join("");
  if (previous !== "" && Number(previous) < series.length) picker.value = previous;
  const showYear = () => {
    const row = series[Number(picker.value)] || series[0], fact = simulationYearFacts(row);
    const amount = (value,format) => value == null ? "자료 없음" : format(value);
    const cash = value => (value < 0 ? "−" : "") + eokMan(Math.abs(value));
    const item = (label,value,note,format=fmtEok) => '<div><span>'+label+'</span><strong>'+amount(value,format)+'</strong><small>'+note+'</small></div>';
    document.getElementById("simulation-year-facts").innerHTML =
      item("명목 순자산",fact.nominal,"해당 연도의 금액") +
      item("실질 순자산",fact.real,"물가를 반영한 오늘 돈 가치") +
      item("연간 지출",fact.expenses,"생활비 + 보험료·의료비",cash) +
      item("연간 유입",fact.income,"연금 + 은퇴 후 소득 · 저축 제외",cash);
  };
  picker.onchange = showYear; showYear();
  drawer.ontoggle = () => {
    toggleLabel();
    if (drawer.open) requestAnimationFrame(() => {
      const mode = document.querySelector("#sim-seg .seg-btn.on")?.dataset.mode || "real";
      simChart(document.getElementById("sim-chart"),series,mode,sim.retire_age,sim.depletion_age);
    });
  };
}
if (typeof module !== "undefined" && module.exports) module.exports = { simulationYearFacts };
