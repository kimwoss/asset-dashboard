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
import news_feed
import sheets_checkpoint
import sheets_holdings
import sheets_fire
import sheets_monthly
import sheets_spending
import sheets_cities
import sheets_sim
import sheets_review
import sheets_yearly

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"
KST = timezone(timedelta(hours=9))

# 체크포인트 탭 시세. (심볼, 표시명, 단위, 배수)
#   배수: yfinance 원값 보정 — JPYKRW=X는 1엔당 원화(≈9.1)라 100엔 기준으로 환산
_US = [
    ("^GSPC", "S&P500", "pt", 1),
    ("^NDX", "NASDAQ100", "pt", 1),
    ("SCHD", "SCHD", "$", 1),
]
_KR = [
    # ^KS200 지수는 넣지 않는다 — 보유 중인 RISE200이 같은 지수를 추종해 중복이고,
    # yfinance의 ^KS200 종가는 ETF보다 며칠씩 밀려 '1일'이 서로 다른 날을 비교했다.
    ("360750.KS", "TIGER 미국S&P500", "₩", 1),
    ("379810.KS", "KODEX 미국나스닥100", "₩", 1),
    ("435420.KS", "TIGER 미국나스닥100채권혼합50", "₩", 1),
    ("458730.KS", "TIGER 미국배당다우존스", "₩", 1),
    ("148020.KS", "RISE200", "₩", 1),
    ("161510.KS", "PLUS 고배당주", "₩", 1),
]
_FX = [
    ("KRW=X", "원/달러", "₩", 1),
    ("JPYKRW=X", "원/엔(100엔)", "₩", 100),
]

# 수익률 구간 (키, 일수) — 증권사 시세 화면과 같은 기준
_HORIZONS = (("d1", 1), ("w1", 7), ("m1", 30), ("y1", 365))


def _quotes(symbols):
    """{symbol: {price, asof, d1, w1, m1, y1}} — 각 기준일 '이전 마지막 거래일' 종가 대비 %.

    2년치를 한 번에 받는다 (yfinance 1콜). period='1y'로 받으면 가장 이른 행이
    365일에 살짝 못 미쳐 1년 수익률이 통째로 비는 종목이 생긴다.
    """
    import pandas as pd
    import yfinance as yf
    out = {}
    try:
        df = yf.download(symbols, period="2y", progress=False, threads=False)["Close"]
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 시세 조회 실패 ({e})")
        return out
    for s in symbols:
        try:
            ser = (df[s] if isinstance(df, pd.DataFrame) else df).dropna()
            if ser.empty:
                print(f"WARN: {s} 시세 없음")
                continue
            price, last_dt = float(ser.iloc[-1]), ser.index[-1]
            q = {"price": price, "asof": last_dt.strftime("%Y-%m-%d")}
            for key, days in _HORIZONS:
                # 기준일 이전(포함) 마지막 거래일 — 주말·휴장 자동 처리
                prior = ser[ser.index <= last_dt - pd.Timedelta(days=days)]
                base = float(prior.iloc[-1]) if len(prior) else None
                q[key] = round((price - base) / base * 100, 2) if base else None
            out[s] = q
        except Exception as e:  # noqa: BLE001
            print(f"WARN: {s} 처리 실패 ({e})")
    return out


def _rows(spec, q, latest=None):
    """(심볼,이름,단위,배수) 명세 + 시세 → 대시보드 행.

    stale: 이 종목의 종가 날짜가 다른 종목보다 뒤처짐 — 그러면 '1일'이 서로 다른 날을
    비교하게 된다. 실제로 ^KS200 지수가 ETF보다 며칠 밀려, 지수 +2.3% / ETF −6.8%로
    보이는 일이 있었다. 숨기지 말고 기준일을 밝힌다.
    """
    rows = []
    for sym, name, unit, mul in spec:
        if sym not in q:
            continue
        v = q[sym]
        rows.append({
            "name": name, "unit": unit, "price": v["price"] * mul, "asof": v["asof"],
            "stale": bool(latest and v["asof"] < latest),
            **{k: v[k] for k, _ in _HORIZONS},
            "change_pct": v["d1"],  # 구버전 렌더러 호환
        })
    return rows


def main():
    now = datetime.now(KST)

    # 1) 지수·ETF·환율 — 1일/1주/1개월/1년 수익률
    q = _quotes([s for s, _, _, _ in _US + _KR + _FX])
    # 시장별 최신 종가일 — 그보다 뒤처진 종목은 stale로 표시 (미국장/국내장은 휴장일이 달라 분리)
    latest = lambda spec: max((q[s]["asof"] for s, _, _, _ in spec if s in q), default=None)
    us, kr = _rows(_US, q, latest(_US)), _rows(_KR, q, latest(_KR))
    fx = [{**r, "rate": r["price"]} for r in _rows(_FX, q, latest(_FX))]  # 환율은 rate 키로도

    # 2) 금융자산 상세 (★주식계좌) — 계좌 평가액·투자 포트폴리오·자산현황 '주식'이
    #    모두 이 '한 번의 읽기'에서 나온다.
    #    예전엔 여기서 배당 제외로 한 번, 아래 5)에서 배당 포함으로 또 한 번 읽었다.
    #    GOOGLEFINANCE는 읽을 때마다 값이 미세하게 달라지고, 둘 중 하나만 실패하면
    #    자산현황(스냅샷 유지)과 투자 포트폴리오(스케일 폴백)의 금액이 어긋났다.
    try:
        financial = sheets_holdings.fetch_holdings()          # 배당 포함
    except Exception as e:  # noqa: BLE001 — 시세·나머지 블록은 계속 나가야 한다
        print(f"WARN: 금융자산 상세 조회 실패 ({type(e).__name__}: {e})")
        financial = None
    fin = financial or {}
    accounts, total = {}, 0
    for h in fin.get("holdings", []):
        key = f"{h['owner']}|{h['account']}"
        accounts[key] = accounts.get(key, 0) + h["value_krw"]
        total += h["value_krw"]

    if not us and not fx and not accounts:
        raise SystemExit("실시간 데이터가 하나도 없음 — 중단 (빈 live.enc 방지)")

    # 3) 관심 뉴스 — 30분마다 최신으로. 실패해도 시세는 나가야 하니 []로 폴백.
    try:
        news = news_feed.fetch_news()
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 뉴스 조회 실패 ({type(e).__name__}: {e})")
        news = []

    # 4) 오늘의 체크포인트(인사말·날씨·운세) — 30분마다 시트에서 다시 읽는다.
    #    모닝 리포트가 이른 아침(≈06:00) 시트에 올리면, 무거운 일별 잡(07:30)을 기다리지 않고
    #    이 30분 잡이 30분 내 웹에 반영한다. 시트 셀 1회 읽기라 AI·쿼터 비용 없음.
    try:
        checkpoint = sheets_checkpoint.fetch_checkpoint(now.date())
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 체크포인트 조회 실패 ({type(e).__name__}: {e})")
        checkpoint = {}

    # 5) 구글시트에서 끌어오는 나머지 블록도 30분마다 갱신 — 사용자가 시트를 고치고
    #    '업데이트하기'를 누르면 최대 30분 내 반영된다. 정적 사이트라 브라우저가 시트를 직접
    #    못 읽으니, 서버(이 잡)가 대신 읽어 live.enc로 발행하고 프론트가 덮어쓴다.
    #    각 읽기는 독립적으로 감싼다 — 하나 실패해도 시세·나머지는 나간다.
    def _safe(fn, label, *a):
        try:
            return fn(*a)
        except Exception as e:  # noqa: BLE001
            print(f"WARN: {label} 조회 실패 ({type(e).__name__}: {e})")
            return None
    # financial(금융자산 상세)은 위 2)에서 이미 한 번만 읽었다 — 여기서 다시 읽지 않는다.
    fire          = _safe(sheets_fire.fetch_fire_summary, "FIRE")
    monthly       = _safe(sheets_monthly.fetch_monthly, "월별 흐름", now.date())
    asset_history = _safe(sheets_yearly.fetch_asset_history, "자산 이력", now.date())
    liabilities   = _safe(sheets_yearly.fetch_liabilities, "부채", now.date())
    spending      = _safe(sheets_spending.fetch_spending, "월간 생활비", now.date()) or {}
    retire_exp    = _safe(sheets_spending.fetch_retirement_expense, "은퇴 생활비", now.date())
    if retire_exp:
        spending["retire"] = retire_exp   # 은퇴 생활비도 30분마다 최신 반영
    cities        = _safe(sheets_cities.fetch_cities, "살고싶은 도시", now.date())
    simulation    = _safe(sheets_sim.fetch_simulation, "은퇴 지도")
    review        = _safe(sheets_review.fetch_review, "연간 리뷰")

    live = {
        "updated_at": now.strftime("%Y-%m-%d %H:%M KST"),
        "updated_iso": now.isoformat(),
        "us": us,
        "kr": kr,
        "fx": fx,
        "fx_usdkrw": round(fin.get("fx") or (fx[0]["rate"] if fx else 0), 2),
        "accounts": accounts,
        "financial_total": total,
        "news": news,
        "checkpoint": checkpoint or None,
        # 시트 파생 블록 (30분 갱신). None이면 프론트가 일별 스냅샷을 유지한다.
        "financial": financial or None,
        "fire": fire or None,
        "monthly": monthly or None,
        "asset_history": asset_history or None,
        "liabilities": liabilities or None,
        "spending": spending or None,
        "cities": cities or None,
        "simulation": simulation or None,
        "review": review or None,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "live.json").write_text(
        json.dumps(live, ensure_ascii=False, indent=1), encoding="utf-8")
    crypto_util.encrypt_file(DATA_DIR / "live.json", DATA_DIR / "live.enc",
                             crypto_util.get_passphrase())
    cp_label = checkpoint.get("date_label", "없음") if checkpoint else "없음"
    sheet_ok = sum(1 for x in (financial, fire, monthly, asset_history, liabilities,
                               spending, cities, simulation, review) if x)
    print(f"OK: live.enc — 미국 {len(us)}건 · 국내 {len(kr)}건 · 환율 {len(fx)}건 · "
          f"계좌 {len(accounts)}개 {total/1e8:.2f}억 · 뉴스 {len(news)}건 · "
          f"체크포인트 {cp_label} · 시트블록 {sheet_ok}/9 ({now:%H:%M} KST)")


if __name__ == "__main__":
    main()
