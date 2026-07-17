# -*- coding: utf-8 -*-
"""실시간 시세 — 30분마다 시세만 갱신해 live.enc를 굽는다.

무거운 잡(update_data.py, AI·KB시세·배당·이력)과 분리한 가벼운 잡.
07:00 스냅샷을 온종일 보는 문제를 해결하되, 자주 바뀌지 않는 것(뉴스·운세·부동산·
배당)은 건드리지 않는다 — 그것들까지 30분마다 돌리면 AI 쿼터만 30배로 늘 뿐이다.

담는 것: 지수·환율(yfinance) + 계좌 평가액(시트 GOOGLEFINANCE)
소요: 시트 2~3콜 + yfinance 1콜 ≈ 30초

산출: docs/data/live.json → live.enc (같은 AES-GCM 봉투 = 대시보드가 같은 비밀번호로 해독)
배포: live-data 고아 브랜치에 매번 새 커밋 + force push → 히스토리 1커밋 고정,
      main이 30분마다 더럽혀지지 않는다. 브라우저는 raw.githubusercontent.com에서
      직접 받는다 (CORS 허용 + 5분 캐시 확인 완료).

※ GOOGLEFINANCE는 15~20분 지연 시세다. 30분 주기 + 지연 = 최대 ~50분 전 값.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import crypto_util
import sheets_holdings

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"
KST = timezone(timedelta(hours=9))

# 체크포인트 탭에 띄우는 지수·환율 (보유 ETF는 시트에서 온다)
_MARKET = [
    ("^GSPC", "S&P500", "pt"),
    ("^NDX", "NASDAQ100", "pt"),
    ("SCHD", "SCHD", "$"),
]
# multiply: yfinance 원값 보정 — JPYKRW=X는 1엔당 원화(≈9.1)라 100엔 기준으로 환산
_FX = [("KRW=X", "원/달러", 1), ("JPYKRW=X", "원/엔(100엔)", 100)]


def _quotes(symbols):
    """{symbol: (price, change_pct)} — 최근 2거래일 종가 대비. 실패 종목은 생략."""
    import yfinance as yf
    import pandas as pd
    out = {}
    try:
        df = yf.download(symbols, period="5d", progress=False, threads=False)["Close"]
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 시세 조회 실패 ({e})")
        return out
    for s in symbols:
        try:
            ser = df[s].dropna() if isinstance(df, pd.DataFrame) else df.dropna()
            if len(ser) < 1:
                continue
            price = float(ser.iloc[-1])
            prev = float(ser.iloc[-2]) if len(ser) >= 2 else price
            out[s] = (price, (price - prev) / prev * 100 if prev else 0.0)
        except Exception:  # noqa: BLE001
            print(f"WARN: {s} 시세 없음")
    return out


def main():
    now = datetime.now(KST)

    # 1) 지수·환율
    q = _quotes([s for s, _, _ in _MARKET] + [s for s, _, _ in _FX])
    us = [{"name": n, "price": q[s][0], "change_pct": round(q[s][1], 2), "unit": u}
          for s, n, u in _MARKET if s in q]
    fx = [{"name": n, "rate": q[s][0] * mul, "change_pct": round(q[s][1], 2)}
          for s, n, mul in _FX if s in q]

    # 2) 계좌 평가액 (시트 GOOGLEFINANCE — 배당은 스킵)
    fin = sheets_holdings.fetch_holdings(with_dividends=False)
    accounts, total = {}, 0
    for h in fin.get("holdings", []):
        key = f"{h['owner']}|{h['account']}"
        accounts[key] = accounts.get(key, 0) + h["value_krw"]
        total += h["value_krw"]

    if not us and not fx and not accounts:
        raise SystemExit("실시간 데이터가 하나도 없음 — 중단 (빈 live.enc 방지)")

    live = {
        "updated_at": now.strftime("%Y-%m-%d %H:%M KST"),
        "updated_iso": now.isoformat(),
        "us": us,
        "fx": fx,
        "fx_usdkrw": round(fin.get("fx") or (fx[0]["rate"] if fx else 0), 2),
        "accounts": accounts,
        "financial_total": total,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "live.json").write_text(
        json.dumps(live, ensure_ascii=False, indent=1), encoding="utf-8")
    crypto_util.encrypt_file(DATA_DIR / "live.json", DATA_DIR / "live.enc",
                             crypto_util.get_passphrase())
    print(f"OK: live.enc — 지수 {len(us)}건 · 환율 {len(fx)}건 · "
          f"계좌 {len(accounts)}개 {total/1e8:.2f}억 ({now:%H:%M} KST)")


if __name__ == "__main__":
    main()
