# -*- coding: utf-8 -*-
"""포트폴리오 전체 갱신: KB시세 + 증권 종가 + 환율 → docs/data/ 산출.

산출물
  docs/data/latest.json   대시보드용 최신 스냅샷
  docs/data/history.csv   자산별 일별 평가액 이력 (long format)
"""
import csv
import json
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
import sheets_sim
import sheets_review
import sheets_yearly

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


def main():
    pf = load_portfolio()
    now = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")
    assets = []

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
    for r in pf.get("real_estate") or []:
        field = r.get("price_field", "매매일반거래가")
        try:
            price_man, base_date = kb_api.latest_price(r["complex_id"], r["area_id"], field)
        except Exception as e:  # noqa: BLE001 - 단지 하나 실패해도 나머지는 진행
            print(f"WARN: KB시세 조회 실패 ({r['name']}): {e}")
            price_man = None
        if price_man is None:
            print(f"WARN: {r['name']} 시세 없음 — 건너뜀")
            continue
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

    # 살고싶은 도시 (🌍이주 대시보드) — Numbeo 기반 도시별 생활비. 실패 시 {} → 탭만 생략.
    cities = sheets_cities.fetch_cities(now.date())

    # 은퇴 100세 지도 (시뮬레이션) · 우리 부부 연간 리뷰 (연간리뷰). 실패 시 {} → 탭만 생략.
    simulation = sheets_sim.fetch_simulation()
    review = sheets_review.fetch_review()

    # 전월 말 기준값 — KPI 3종의 '전월 대비'. history.csv를 다시 쓰기 전에 읽어야 한다.
    prev_month = prev_month_baseline(now.date(), DATA_DIR / "history.csv")
    if prev_month:
        print(f"OK: 전월({prev_month['key']}) 기준 순자산 {prev_month['net_krw']/1e8:.2f}억 "
              f"· 출처 {'우리 실측' if prev_month['source'] == 'measured' else '시트 소계'}")

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
        "cities": cities,
        "simulation": simulation,
        "review": review,
        "prev_month": prev_month,
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
