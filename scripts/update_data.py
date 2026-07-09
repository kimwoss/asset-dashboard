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
    df = yf.download(tickers, period="7d", progress=False, threads=False)["Close"]
    if len(tickers) == 1:
        df = df.to_frame(tickers[0])
    out = {}
    for t in tickers:
        series = df[t].dropna()
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
    tickers = sorted({s["ticker"] for s in sec} | {"KRW=X"})
    prices = fetch_security_prices(tickers)
    if "KRW=X" not in prices:
        raise SystemExit("환율(KRW=X) 조회 실패 — 중단")
    fx, fx_date = prices["KRW=X"]

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

    # 3) 현금성
    for c in pf.get("cash") or []:
        assets.append({
            "name": c["name"], "ticker": "", "owner": c.get("owner", ""),
            "category": "현금", "quantity": 1, "price": c["amount_krw"],
            "currency": "KRW", "asof": today, "value_krw": c["amount_krw"],
        })

    if not assets:
        raise SystemExit("자산이 하나도 계산되지 않음 — 중단")

    # 4) latest.json
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    total = sum(a["value_krw"] for a in assets)
    snapshot = {
        "updated_at": now.strftime("%Y-%m-%d %H:%M KST"),
        "fx_usdkrw": round(fx, 2),
        "fx_asof": fx_date,
        "total_krw": total,
        "assets": assets,
    }
    with open(DATA_DIR / "latest.json", "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=1)

    # 5) history.csv — 오늘 자 행은 갈아끼움 (하루 2회 실행 대응)
    hist_path = DATA_DIR / "history.csv"
    fields = ["date", "name", "owner", "category", "value_krw"]
    rows = []
    if hist_path.exists():
        with open(hist_path, encoding="utf-8", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["date"] != today]
    rows += [{"date": today, "name": a["name"], "owner": a["owner"],
              "category": a["category"], "value_krw": a["value_krw"]} for a in assets]
    with open(hist_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"OK: 자산 {len(assets)}건, 총 {total / 1e8:.2f}억원 (환율 {fx:.0f})")


if __name__ == "__main__":
    main()
