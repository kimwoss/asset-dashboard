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

    # 4) 평가액 자산 (실시간 미연동, 고정 원화 평가액)
    for m in pf.get("manual_assets") or []:
        assets.append({
            "name": m["name"], "ticker": "", "owner": m.get("owner", ""),
            "category": m.get("category", "기타"), "quantity": 1,
            "price": m["amount_krw"], "currency": "KRW",
            "asof": m.get("asof", today), "value_krw": m["amount_krw"],
            "note": m.get("note", ""),
        })

    if not assets:
        raise SystemExit("자산이 하나도 계산되지 않음 — 중단")

    # 5) 부채
    liabilities = [{
        "name": l["name"], "owner": l.get("owner", ""),
        "amount_krw": l["amount_krw"], "note": l.get("note", ""),
    } for l in (pf.get("liabilities") or [])]

    # 6) latest.json
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    gross = sum(a["value_krw"] for a in assets)
    debt = sum(l["amount_krw"] for l in liabilities)
    net = gross - debt
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
    }
    with open(DATA_DIR / "latest.json", "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=1)

    # 7) history.csv — 순자산 추이용. 오늘 자 행은 갈아끼움 (하루 2회 실행 대응)
    #    kind: asset(+) / liability(-)
    hist_path = DATA_DIR / "history.csv"
    fields = ["date", "kind", "name", "owner", "category", "value_krw"]
    rows = []
    if hist_path.exists():
        with open(hist_path, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("date") == today:
                    continue
                r.setdefault("kind", "asset")  # 구 포맷 마이그레이션
                rows.append({k: r.get(k, "") for k in fields})
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
