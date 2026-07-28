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

# 직전 발행본 — 캐시 재사용의 원본. live-data 브랜치는 public이라 인증 없이 받는다.
PREV_URL = "https://raw.githubusercontent.com/kimwoss/asset-dashboard/live-data/live.enc"

# ── 블록별 수명(TTL) ───────────────────────────────────────────────────────────
# 크론은 */30이지만 GitHub이 실제로 주는 주기는 중앙값 100분이다(실측 2026-07, 기대의 27%).
# 그 100분마다 시트 블록 9개를 전부 다시 읽어봐야 대부분은 같은 값이다 — live/latest를
# 12시간 차이로 비교했을 때 7개(asset_history·cities·liabilities·monthly·review·spending·
# checkpoint)가 완전히 동일했다. 그래서 '얼마나 자주 실제로 바뀌는가'로 수명을 나눈다.
#   0분  = 매 실행 (시세 연동이라 늘 바뀜)
#   그 외 = 그 시간이 지나야 다시 읽는다. 그 전에는 직전 발행본 값을 그대로 싣는다.
# 값이 아니라 '읽기'를 아끼는 것이므로 페이로드는 항상 완전하다.
TTL_MIN = {
    "financial":     0,     # ★주식계좌 GOOGLEFINANCE — 계좌 평가액, 매번
    "checkpoint":    0,     # 셀 1개 읽기라 저렴 + 모닝 리포트를 늦지 않게 잡아야 함
    "fire":          180,   # ★종합 목표치. 달성률은 프론트가 순자산으로 재계산한다
    "simulation":    180,   # 은퇴 지도 — 순자산 연동이지만 하루 단위로 봐도 무방
    "spending":      180,   # 가계부. 사용자가 시트를 고치면 3시간 내 반영
    "asset_history": 180,
    "liabilities":   180,
    "monthly":       180,
    "cities":        720,   # 🌍이주 대시보드 — 도시를 더할 때만 바뀐다
    "review":        720,   # 연간 리뷰 — 거의 안 바뀐다
}


def _load_prev():
    """직전 live.enc를 받아 (payload, meta) 로. 실패하면 ({}, {}) — 전체 갱신으로 떨어진다.

    복호화 중간산물은 반드시 임시 디렉터리에 둔다. docs/data 안에 두면 일별 잡의
    `git add docs/data`에 평문 금융데이터가 딸려 들어갈 수 있다.
    """
    import tempfile
    import urllib.request
    try:
        raw = urllib.request.urlopen(PREV_URL + "?t=" + str(int(datetime.now().timestamp())),
                                     timeout=30).read()
        with tempfile.TemporaryDirectory() as td:
            enc, out = Path(td) / "prev.enc", Path(td) / "prev.json"
            enc.write_bytes(raw)
            crypto_util.decrypt_file(enc, out, crypto_util.get_passphrase())
            prev = json.loads(out.read_text(encoding="utf-8"))
        return prev, (prev.get("_fetched") or {})
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 직전 live.enc 불러오기 실패 ({type(e).__name__}: {e}) — 전체 갱신")
        return {}, {}


def _fresh(key: str, meta: dict, now: datetime) -> bool:
    """이 블록을 지금 다시 읽어야 하나? (수명 만료 또는 직전 값 없음)"""
    ttl = TTL_MIN.get(key, 0)
    if ttl <= 0:
        return True
    stamp = meta.get(key)
    if not stamp:
        return True
    try:
        age = (now - datetime.fromisoformat(stamp)).total_seconds() / 60
    except ValueError:
        return True
    return age >= ttl

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

    # 4) 직전 발행본 — 수명이 남은 블록은 여기서 그대로 가져다 쓴다.
    prev, meta = _load_prev()
    meta = dict(meta)
    reused, refetched = [], []

    def _block(key, fn, *a):
        """수명이 남았으면 직전 값 재사용, 아니면 새로 읽는다. 읽기 실패 시에도 직전 값 유지.

        종전에는 실패하면 None을 실어 보내 프론트가 아침 스냅샷(최대 12시간 전)으로
        후퇴했다. 직전 성공값이 있는데 버릴 이유가 없다.
        """
        if not _fresh(key, meta, now):
            reused.append(key)
            return prev.get(key)
        try:
            v = fn(*a)
        except Exception as e:  # noqa: BLE001
            print(f"WARN: {key} 조회 실패 ({type(e).__name__}: {e}) — 직전 값 유지")
            return prev.get(key)
        if not v:
            return prev.get(key)
        meta[key] = now.isoformat()
        refetched.append(key)
        return v

    # 오늘의 체크포인트(인사말·날씨·운세) — 셀 1개 읽기라 매 실행 확인한다.
    # 모닝 리포트가 이른 아침(≈06:00) 시트에 올리면 무거운 일별 잡(07:30)을 기다리지 않고
    # 이 잡이 먼저 웹에 반영한다.
    checkpoint = _block("checkpoint", sheets_checkpoint.fetch_checkpoint, now.date()) or {}

    # 5) 시트 파생 블록 — 수명(TTL_MIN)이 만료된 것만 새로 읽는다.
    #    정적 사이트라 브라우저가 시트를 직접 못 읽으니 서버(이 잡)가 대신 읽어 발행한다.
    #    financial은 2)에서 이미 읽었다(TTL 0 = 매 실행이라 어차피 지금 읽을 차례다).
    #    여기서 또 읽으면 GOOGLEFINANCE가 호출마다 값을 미세하게 달리 주기 때문에
    #    accounts(2번 결과)와 financial(5번 결과)이 어긋난다 — 그 한 번을 그대로 쓴다.
    if financial:
        meta["financial"] = now.isoformat()
        refetched.append("financial")
    else:
        financial = prev.get("financial")   # 읽기 실패 → 직전 발행본 유지
    fire          = _block("fire", sheets_fire.fetch_fire_summary)
    monthly       = _block("monthly", sheets_monthly.fetch_monthly, now.date())
    asset_history = _block("asset_history", sheets_yearly.fetch_asset_history, now.date())
    liabilities   = _block("liabilities", sheets_yearly.fetch_liabilities, now.date())
    cities        = _block("cities", sheets_cities.fetch_cities, now.date())
    simulation    = _block("simulation", sheets_sim.fetch_simulation)
    review        = _block("review", sheets_review.fetch_review)

    # 생활비 = 가계부(시각화) + 은퇴 계획(참조.연간 생활비). 한 블록으로 묶어 수명을 함께 관리한다.
    spending = _block("spending", lambda d: {
        **(sheets_spending.fetch_spending(d) or {}),
        **({"retire": r} if (r := sheets_spending.fetch_retirement_expense(d)) else {}),
    }, now.date())

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
        # 시트 파생 블록. 새로 읽었거나(만료) 직전 발행본에서 물려받은 값. None이면 프론트가
        # 일별 스냅샷을 쓴다 — 이제는 읽기에 실패해도 직전 값이 있으면 None으로 떨어지지 않는다.
        "financial": financial or None,
        "fire": fire or None,
        "monthly": monthly or None,
        "asset_history": asset_history or None,
        "liabilities": liabilities or None,
        "spending": spending or None,
        "cities": cities or None,
        "simulation": simulation or None,
        "review": review or None,
        # 블록별 마지막 '실제 조회' 시각 — 다음 실행이 수명을 재는 기준이자, 화면에 신선도를 밝히는 근거
        "_fetched": meta,
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
    print(f"    조회 {len(refetched)}건 {refetched} · 재사용 {len(reused)}건 {reused}")


if __name__ == "__main__":
    main()
