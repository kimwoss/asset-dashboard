# -*- coding: utf-8 -*-
"""포트폴리오 전체 갱신: KB시세 + 증권 종가 + 환율 → docs/data/ 산출.

산출물
  docs/data/latest.json   대시보드용 최신 스냅샷
  docs/data/history.csv   자산별 일별 평가액 이력 (long format)
"""
import csv
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml
import yfinance as yf

import kb_api
import sheets_fire
import sheets_holdings
import sheets_monthly
import sheets_checkpoint
import sheets_spending
import sheets_cities
import sheets_officetel
import sheets_sim
import sheets_review
import sheets_yearly
import sheets_annual

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"
KST = timezone(timedelta(hours=9))


def load_portfolio():
    with open(ROOT / "config" / "portfolio.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_security_prices(tickers):
    """티커별 최근 종가. 반환: {ticker: (price, 'YYYY-MM-DD')}"""
    if not tickers:
        return {}
    close = yf.download(tickers, period="7d", progress=False, threads=False)["Close"]
    import pandas as pd
    out = {}
    for t in tickers:
        # close는 티커 수/버전에 따라 Series 또는 DataFrame일 수 있음 — 방어적으로 처리
        if isinstance(close, pd.Series):
            series = close.dropna()
        elif t in getattr(close, "columns", []):
            series = close[t].dropna()
        elif getattr(close, "shape", (0, 0))[1:] == (1,):
            series = close.iloc[:, 0].dropna()
        else:
            print(f"WARN: {t} 가격 조회 실패")
            continue
        if series.empty:
            print(f"WARN: {t} 가격 조회 실패")
            continue
        out[t] = (float(series.iloc[-1]), series.index[-1].strftime("%Y-%m-%d"))
    return out


def prev_month_baseline(today, hist_path):
    """전월 말 기준 {key, net_krw, gross_krw, debt_krw, source}. 없으면 {}.

    KPI를 '어제 대비'가 아니라 '전월 대비'로 읽기 위한 기준값. 자산은 하루 단위로는
    거의 움직이지 않아 어제 대비는 노이즈였다.

    1순위 history.csv의 전월 마지막 실측 행 — 지금 값과 완전히 같은 방식으로 계산돼
           비교가 깨끗하다. 일별 기록을 2026-07-15에 시작했으므로 2026-08부터 가능.
    2순위 ★월별자산 전월 소계 — 그 전까지의 유일한 과거값. 시트는 부동산을 추정으로
           굴리므로 우리 평가액과 계통 오차가 있다 (source로 표시해 밝힌다).
    """
    y, m = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    key = f"{y}-{m:02d}"

    # 1순위 — 우리 실측
    if hist_path.exists():
        by_date = {}
        with open(hist_path, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                d = r.get("date", "")
                if not d.startswith(key) or r.get("kind") not in ("asset", "liability"):
                    continue
                acc = by_date.setdefault(d, {"gross": 0.0, "debt": 0.0})
                v = float(r.get("value_krw") or 0)
                if r["kind"] == "asset":
                    acc["gross"] += v
                else:
                    acc["debt"] += -v  # 부채는 음수로 저장돼 있다
        if by_date:
            last = by_date[max(by_date)]
            return {"key": key, "source": "measured",
                    "gross_krw": round(last["gross"]), "debt_krw": round(last["debt"]),
                    "net_krw": round(last["gross"] - last["debt"])}

    # 2순위 — 시트 소계
    s = sheets_monthly.month_summary(y, m)
    if not s:
        print(f"WARN: {key} 기준값 없음 — 전월 대비 생략")
        return {}
    return {"key": key, "source": "sheet",
            "gross_krw": round(s["gross"]), "debt_krw": round(s["debt"]),
            "net_krw": round(s["net"])}


def prev_day_baseline(today, hist_path):
    """전일(오늘 이전 가장 최근 기록일) 기준 {key, gross_krw, debt_krw, net_krw}. 없으면 {}.

    history.csv의 asset/liability 행(일별 실측)만 센다. 일별 기록을 2026-07-15에 시작했으므로
    그 이후로 하루라도 지나면 채워진다. 오늘 자 행을 다시 쓰기 전에 호출해야 한다.
    """
    today_str = today.strftime("%Y-%m-%d")
    if not hist_path.exists():
        return {}
    by_date = {}
    with open(hist_path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            d = r.get("date", "")
            if not d or d >= today_str or r.get("kind") not in ("asset", "liability"):
                continue
            acc = by_date.setdefault(d, {"gross": 0.0, "debt": 0.0})
            v = float(r.get("value_krw") or 0)
            if r["kind"] == "asset":
                acc["gross"] += v
            else:
                acc["debt"] += -v  # 부채는 음수로 저장돼 있다
    if not by_date:
        return {}
    key = max(by_date)
    last = by_date[key]
    return {"key": key, "gross_krw": round(last["gross"]), "debt_krw": round(last["debt"]),
            "net_krw": round(last["gross"] - last["debt"])}


def main():
    pf = load_portfolio()
    now = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")
    assets = []

    # 직전 스냅샷 — 외부 API가 죽었을 때의 폴백 원본이자 급감 감지의 기준.
    prev_snap = {}
    _prev_path = DATA_DIR / "latest.json"
    if _prev_path.exists():
        try:
            with open(_prev_path, encoding="utf-8") as f:
                prev_snap = json.load(f)
        except Exception as e:  # noqa: BLE001
            print(f"WARN: 직전 스냅샷 읽기 실패 ({type(e).__name__}: {e}) — 폴백 없이 진행")
    prev_assets = {a.get("name"): a for a in (prev_snap.get("assets") or []) if a.get("name")}

    # 1) 환율 + 증권
    sec = pf.get("securities") or []
    has_us = any(s.get("market", "US").upper() == "US" for s in sec)
    tickers = sorted({s["ticker"] for s in sec} | {"KRW=X"})
    prices = fetch_security_prices(tickers)
    if "KRW=X" in prices:
        fx, fx_date = prices["KRW=X"]
    elif has_us:
        raise SystemExit("환율(KRW=X) 조회 실패 — USD 자산이 있어 중단")
    else:
        # USD 자산이 없으면 환율은 정보성. 마지막 스냅샷 값 재사용, 없으면 표시만.
        prev = DATA_DIR / "latest.json"
        fx, fx_date = 0, "N/A"
        if prev.exists():
            try:
                o = json.load(open(prev, encoding="utf-8"))
                fx, fx_date = o.get("fx_usdkrw", 0), o.get("fx_asof", "N/A")
            except Exception:  # noqa: BLE001
                pass
        print("WARN: 환율 조회 실패 (USD 자산 없음) — 정보성 값만 표시")

    for s in sec:
        if s["ticker"] not in prices:
            continue
        price, asof = prices[s["ticker"]]
        is_us = s.get("market", "US").upper() == "US"
        value_krw = price * s["quantity"] * (fx if is_us else 1)
        assets.append({
            "name": s.get("name") or s["ticker"],
            "ticker": s["ticker"],
            "owner": s.get("owner", ""),
            "category": "미국주식" if is_us else "한국주식",
            "quantity": s["quantity"],
            "price": round(price, 4),
            "currency": "USD" if is_us else "KRW",
            "asof": asof,
            "value_krw": round(value_krw),
        })

    # 2) 부동산 (KB시세, 만원 단위 → 원)
    #    ⚠️ KB API가 일시적으로 죽어도 21억짜리 집을 자산에서 지워선 안 된다.
    #    2026-07-28 실제 사고: urlopen timeout 두 건으로 아파트 2채(21.5억)가 조용히 빠져
    #    순자산 −3.24억짜리 스냅샷이 'success'로 발행됐다. 그래서
    #      ① 실패하면 직전 스냅샷의 마지막 시세를 그대로 들고 가고(기준일도 그때 값 유지)
    #      ② 폴백조차 없으면 발행하지 않고 잡을 실패시킨다.
    for r in pf.get("real_estate") or []:
        field = r.get("price_field", "매매일반거래가")
        try:
            price_man, base_date = kb_api.latest_price(r["complex_id"], r["area_id"], field)
        except Exception as e:  # noqa: BLE001 - 단지 하나 실패해도 나머지는 진행
            print(f"WARN: KB시세 조회 실패 ({r['name']}): {e}")
            price_man = None
        if price_man is None:
            old = prev_assets.get(r["name"])
            if old and old.get("value_krw"):
                assets.append({**old, "note": f"KB시세 조회 실패 — {old.get('asof', '직전')} 시세 유지"})
                print(f"WARN: {r['name']} 시세 없음 — 직전 값 {old['value_krw']/1e8:.2f}억 유지 "
                      f"(기준일 {old.get('asof', '?')})")
                continue
            raise SystemExit(
                f"ERROR: {r['name']} 시세를 못 받았고 직전 값도 없습니다 — "
                f"자산이 통째로 빠진 스냅샷을 발행하지 않도록 중단합니다.")
        assets.append({
            "name": r["name"],
            "ticker": "",
            "owner": r.get("owner", ""),
            "category": "부동산",
            "quantity": 1,
            "price": price_man * 10000,
            "currency": "KRW",
            "asof": base_date or today,
            "value_krw": price_man * 10000,
        })

    # KB 신선도 점검 — KB시세는 매주 금요일 08:00 KST에 갱신된다. 예약 실행이 밀리거나
    # 유실되면 지난주 시세를 그대로 들고 가는데, '값이 안 오른 주'와 겉으로 구분이 안 돼
    # 조용히 묵는다. 2026-08-07 실제: 금요일 크론이 통째로 유실돼 송천센트레빌 +1,500만이
    # 반나절 늦게 반영됐고, 로그만 봐선 정상 실행과 똑같아 보였다. 그래서 명시적으로 남긴다.
    friday = now.date() - timedelta(days=(now.weekday() - 4) % 7)
    for a in assets:
        if a["category"] == "부동산" and str(a.get("asof", "")) < friday.isoformat():
            print(f"WARN: {a['name']} KB시세 기준일이 {a.get('asof')}입니다 — "
                  f"이번 주 금요일({friday}) 시세가 아직 안 잡혔습니다. "
                  f"KB 갱신(금 08:00) 전에 실행됐거나 금요일 실행이 유실된 것입니다.")

    # 3) 현금성 (cash 목록 — manual_assets로 통합 가능하나 하위호환 유지)
    for c in pf.get("cash") or []:
        assets.append({
            "name": c["name"], "ticker": "", "owner": c.get("owner", ""),
            "category": "현금", "quantity": 1, "price": c["amount_krw"],
            "currency": "KRW", "asof": today, "value_krw": c["amount_krw"],
        })

    # 4) 평가액 자산 — 금융 부분을 구글드라이브(★주식계좌·★월별자산)와 연계해 두 탭 액수를 일치시킨다.
    #    금융자산 상세를 먼저 읽어(★주식계좌) 소유자별 합을 구하고, 주식계좌 값을 그걸로 대체한다.
    financial = sheets_holdings.fetch_holdings()  # ★주식계좌 (금융자산 탭과 동일 소스)
    owner_sum: Dict[str, int] = {}
    for h in financial.get("holdings", []):
        owner_sum[h["owner"]] = owner_sum.get(h["owner"], 0) + h["value_krw"]
    other_fin = sheets_yearly.fetch_other_assets(now.date())  # 회사주식·외화 (★연도별자산 올해 열)
    residence = sheets_yearly.fetch_residence_deposits(now.date())  # 거주 전세보증금(파크하비오 등)

    for m in pf.get("manual_assets") or []:
        name, cat, owner = m["name"], m.get("category", "기타"), m.get("owner", "")
        value, note = m["amount_krw"], m.get("note", "")
        if cat == "주식" and owner in owner_sum:
            value, note = owner_sum[owner], "★주식계좌 실시간 연동"   # 금융자산 탭과 동일 값
        elif cat == "현금" and name.startswith("현금성"):
            # 이 별도 현금은 시트 순자산에 없다(이미 CMA로 계좌에 포함). 시트가 세는 회사주식·외화로
            # 대체해 구글드라이브 순자산과 정확히 맞춘다. 시트값이 0이면 이 줄은 생략.
            if other_fin <= 0:
                continue
            name, value, note = "회사주식·외화", other_fin, "★연도별자산 기준"
        elif cat == "전세보증금" and residence:
            # 거주 전세보증금은 시트에서 읽어 아래에서 추가 — yaml 값은 중복이므로 생략(시트 실패 시만 사용)
            continue
        assets.append({
            "name": name, "ticker": "", "owner": owner,
            "category": cat, "quantity": 1,
            "price": value, "currency": "KRW",
            "asof": m.get("asof", today), "value_krw": value, "note": note,
        })

    # 거주 전세보증금 — ★월별자산 기준 (실패 시 위 yaml manual_assets가 이미 추가됨)
    for d in residence:
        assets.append({
            "name": d["name"], "ticker": "", "owner": d["owner"],
            "category": "전세보증금", "quantity": 1,
            "price": d["value_krw"], "currency": "KRW",
            "asof": today, "value_krw": d["value_krw"], "note": d.get("note", ""),
        })

    if not assets:
        raise SystemExit("자산이 하나도 계산되지 않음 — 중단")

    # 5) 부채 — 원 소스는 ★월별자산 26~35행 (사용자가 매월초 잔액 수기 갱신).
    #    시트를 못 읽으면 portfolio.yaml 값으로 폴백 (스냅샷이 오래됐을 수 있음).
    liabilities = sheets_yearly.fetch_liabilities(now.date())
    if not liabilities:
        print("WARN: 부채를 yaml 폴백으로 사용 — ★월별자산 연결 확인 필요")
        liabilities = [{
            "name": l["name"], "owner": l.get("owner", ""),
            "kind": l.get("kind", "loan"),
            # target: 이 부채가 조달한 자산군 — 대시보드가 순자산 배분에서 상계한다
            "target": l.get("target", "무담보"),
            "amount_krw": l["amount_krw"], "note": l.get("note", ""),
        } for l in (pf.get("liabilities") or [])]

    # 6) latest.json
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    gross = sum(a["value_krw"] for a in assets)
    debt = sum(l["amount_krw"] for l in liabilities)
    net = gross - debt

    # 최종 안전장치 — 총자산이 직전 대비 급감하면 발행하지 않는다.
    # 개별 폴백을 다 통과해도, 다른 소스(시트·계좌)가 통째로 비면 여기서 걸린다.
    # 집을 실제로 팔아 정상적으로 줄어든 경우엔 ALLOW_BIG_DROP=1로 한 번 통과시킨다.
    prev_gross = prev_snap.get("gross_krw") or 0
    if prev_gross and gross < prev_gross * 0.8 and os.environ.get("ALLOW_BIG_DROP") != "1":
        raise SystemExit(
            f"ERROR: 총자산이 직전 {prev_gross/1e8:.2f}억 → {gross/1e8:.2f}억으로 "
            f"{(1 - gross / prev_gross) * 100:.0f}% 급감했습니다 — 데이터 누락이 의심되어 발행을 중단합니다. "
            f"실제 매각 등 정상적인 감소라면 ALLOW_BIG_DROP=1 로 재실행하세요.")
    # FIRE 목표 요약 (⭐️분당부부_MASTER ★종합 탭). 실패 시 {} — 섹션만 생략.
    # 달성률은 대시보드가 위 net(실시간)으로 재계산한다 → 시트는 목표·가정치만 제공.
    fire = sheets_fire.fetch_fire_summary()
    if fire:
        print(f"OK: FIRE 목표 {fire.get('target_basic', 0)/1e8:.2f}억(기본)/"
              f"{fire.get('target_rich', 0)/1e8:.2f}억(부자) · 목표 {fire.get('target_year')}년")

    # (financial = ★주식계좌 상세는 위 4)에서 이미 읽었다 — 재사용)

    # 월별 흐름 — 이번 달 칸에 자동 기록(upsert)한 뒤 전체 이력을 읽어온다.
    # 매일 덮어쓰므로 달이 바뀌면 직전 달 '말일' 값이 자연히 확정된다.
    #  (1) 금융자산 = ★주식계좌 계좌별 합계 (GOOGLEFINANCE는 '지금'만 알기에 얼려 저장)
    #  (2) 부동산   = KB 실시세 (기존 시트 추정 수식 =U*1.009 를 실값으로 대체)
    if financial.get("holdings"):
        sheets_monthly.write_current_month(financial["holdings"], now.date())
    re_assets = [{"name": a["name"], "value_krw": a["value_krw"]}
                 for a in assets if a.get("category") == "부동산"]
    sheets_monthly.write_current_month_realestate(re_assets, now.date())
    monthly = sheets_monthly.fetch_monthly(now.date())
    # 자산 상세용 전월·전년 이력 (각 항목의 증감 표시). 실패 시 {} → 증감만 생략.
    asset_history = sheets_yearly.fetch_asset_history(now.date())

    # 오늘의 체크포인트 — 분당부부 모닝 리포트(별도 private 레포)가 시트에 남긴 페이로드.
    checkpoint = sheets_checkpoint.fetch_checkpoint(now.date())

    # 월간 생활비 (시각화 탭 '상세항목별 지출 금액'). 실패 시 {} → 탭만 생략.
    spending = sheets_spending.fetch_spending(now.date()) or {}
    # 은퇴 이후 생활비 계획 (참조.연간 생활비 탭). 같은 탭에 붙여 대시보드가 함께 렌더.
    retire_exp = sheets_spending.fetch_retirement_expense(now.date())
    if retire_exp:
        spending["retire"] = retire_exp

    # 연도별 소득·지출 (시각화 탭 '연도별 소득·지출 요약'). 저축률 KPI와 연도별 표의 원본.
    annual_flow = sheets_annual.fetch_annual_flow()

    # 살고싶은 도시 (🌍이주 대시보드) — Numbeo 기반 도시별 생활비. 실패 시 {} → 탭만 생략.
    cities = sheets_cities.fetch_cities(now.date())

    # 다음 후보집 ((ing)2027년 오피스텔) — 이사 후보 타입 카탈로그 + 기준 통과 매물.
    # 매물 입력은 사람이 한다 (부동산 사이트 전부 robots.txt로 자동수집 금지).
    officetel = sheets_officetel.fetch_officetel()

    # 은퇴 100세 지도 (시뮬레이션) · 우리 부부 연간 리뷰 (연간리뷰). 실패 시 {} → 탭만 생략.
    simulation = sheets_sim.fetch_simulation()
    review = sheets_review.fetch_review()

    # 전일·전월·전년 기준값 — KPI 3종(순자산·총자산·부채)의 대비 표기용.
    # history.csv를 다시 쓰기 전에 읽어야 한다. 전년은 ★연도별자산 작년 열(asset_history.totals.y1).
    prev_month = prev_month_baseline(now.date(), DATA_DIR / "history.csv")
    prev_day = prev_day_baseline(now.date(), DATA_DIR / "history.csv")
    _t = (asset_history or {}).get("totals") or {}
    prev_year = {}
    if (_t.get("net") or {}).get("y1"):
        prev_year = {"key": (asset_history or {}).get("prev_year") or str(now.year - 1),
                     "gross_krw": _t["gross"]["y1"], "debt_krw": _t["debt"]["y1"], "net_krw": _t["net"]["y1"]}
    if prev_month:
        print(f"OK: 전월({prev_month['key']}) 기준 순자산 {prev_month['net_krw']/1e8:.2f}억 "
              f"· 출처 {'우리 실측' if prev_month['source'] == 'measured' else '시트 소계'}"
              + (f" · 전일 {prev_day['key']}" if prev_day else "")
              + (f" · 전년 {prev_year['key']} {prev_year['net_krw']/1e8:.2f}억" if prev_year else ""))

    snapshot = {
        "updated_at": now.strftime("%Y-%m-%d %H:%M KST"),
        "fx_usdkrw": round(fx, 2),
        "fx_asof": fx_date,
        "gross_krw": gross,
        "debt_krw": debt,
        "net_krw": net,
        "total_krw": net,  # 하위호환: total = 순자산
        "assets": assets,
        "liabilities": liabilities,
        "fire": fire,
        "financial": financial,
        "monthly": monthly,
        "asset_history": asset_history,
        "checkpoint": checkpoint,
        "spending": spending,
        "annual_flow": annual_flow,
        "cities": cities,
        "officetel": officetel,
        "simulation": simulation,
        "review": review,
        "prev_day": prev_day,
        "prev_month": prev_month,
        "prev_year": prev_year,
    }
    with open(DATA_DIR / "latest.json", "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=1)

    # 7) history.csv — 순자산 추이용. 오늘 자 행은 갈아끼움 (하루 2회 실행 대응)
    #    kind: asset(+) / liability(-) / seed(순자산 이력 1행)
    #    날짜별 value_krw 합계 = 그 날의 순자산 (대시보드가 이 방식으로 추이 계산)
    hist_path = DATA_DIR / "history.csv"
    fields = ["date", "kind", "name", "owner", "category", "value_krw"]

    # 마스터 시트 순자산 이력 시드 (과거 고정값, 오늘 이전 날짜만)
    # YAML이 날짜를 date 객체로 파싱하므로 문자열로 강제 변환 (CSV 비교/중복제거 위해)
    seed = {str(s["date"]): int(s["net_krw"]) for s in (pf.get("networth_history") or [])}
    seed_dates = set(seed)

    rows = []
    if hist_path.exists():
        with open(hist_path, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                # 오늘 자와 시드 날짜는 아래에서 새로 채워넣음
                if r.get("date") == today or r.get("date") in seed_dates:
                    continue
                r.setdefault("kind", "asset")  # 구 포맷 마이그레이션
                rows.append({k: r.get(k, "") for k in fields})
    for d, net_v in sorted(seed.items()):
        rows.append({"date": d, "kind": "seed", "name": "순자산",
                     "owner": "", "category": "순자산", "value_krw": net_v})
    for a in assets:
        rows.append({"date": today, "kind": "asset", "name": a["name"],
                     "owner": a["owner"], "category": a["category"], "value_krw": a["value_krw"]})
    for l in liabilities:
        rows.append({"date": today, "kind": "liability", "name": l["name"],
                     "owner": l["owner"], "category": "부채", "value_krw": -l["amount_krw"]})
    with open(hist_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"OK: 자산 {len(assets)}건 총 {gross / 1e8:.2f}억 − 부채 {debt / 1e8:.2f}억 "
          f"= 순자산 {net / 1e8:.2f}억 (환율 {fx:.0f})")


if __name__ == "__main__":
    main()
