# -*- coding: utf-8 -*-
"""KB부동산(kbland.kr) 비공식 API 클라이언트.

인증 불필요. 모든 금액 단위: 만원.
"""
import json
import random
import ssl
import time
import urllib.parse
import urllib.request

BASE = "https://api.kbland.kr"

# 정상 응답은 0.1초 안팎이다(실측 2026-07-31: 10회 최소 0.09s·중앙 0.11s·최대 0.15s).
# 그래서 20초를 넘긴다는 건 '느리다'가 아니라 '죽었다'는 뜻이다.
#   · 타임아웃을 10초로 줄인다 — 정상 대비 65배 여유. 멈춘 연결은 빨리 끊어야 다음 시도가 빨라진다.
#   · 대신 '몇 번' 재시도가 아니라 '몇 분' 버틸지로 바꾼다. 살아 있으면 0.1초에 끝나므로
#     재시도를 넉넉히 줘도 평소 비용은 0이고, 잠깐의 장애는 통째로 흡수된다.
# 2026-07-28 사고: 3회(≈66초) 재시도가 모두 타임아웃 → 21.5억짜리 집 두 채가 자산에서 빠졌다.
TIMEOUT_S = 10
RETRY_WINDOW_S = 300     # 이 시간 동안은 포기하지 않는다 (일별 잡이라 5분은 감당 가능)
BACKOFF_CAP_S = 30
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://kbland.kr/",
    "Accept": "application/json",
}

# 사내망 등에서 TLS를 재서명하는 프록시를 만나면 검증이 실패한다.
# 우선 정상 검증으로 시도하고, 인증서 검증 오류일 때만 검증을 완화해 재시도한다.
# (공개·읽기전용 시세 API여서 위험이 낮고, CI 러너에서는 검증 경로만 사용됨)
_UNVERIFIED = ssl._create_unverified_context()


def _open(url, insecure=False):
    req = urllib.request.Request(url, headers=HEADERS)
    ctx = _UNVERIFIED if insecure else None
    return urllib.request.urlopen(req, timeout=TIMEOUT_S, context=ctx)


def _is_ssl_error(e):
    """URLError로 감싸인 경우까지 포함해 TLS 인증서 검증 오류인지 판별."""
    seen = set()
    while e is not None and id(e) not in seen:
        if isinstance(e, ssl.SSLError):
            return True
        seen.add(id(e))
        e = getattr(e, "reason", None) or getattr(e, "__cause__", None)
    return False


def _get(path, params, window_s=RETRY_WINDOW_S):
    """KB API 호출. window_s 동안 지수 백오프로 버틴다.

    살아 있으면 첫 시도 0.1초로 끝나므로 평소 비용은 없다. 죽어 있을 때만 시간을 쓴다.
    끝내 실패하면 마지막 예외를 올려 호출자(update_data)의 폴백·중단 로직으로 넘긴다.
    """
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    deadline = time.monotonic() + window_s
    delay, attempt, last_err, insecure = 1.0, 0, None, False

    while True:
        attempt += 1
        try:
            with _open(url, insecure=insecure) as resp:
                data = json.load(resp)
            body = data.get("dataBody", {})
            if body.get("message") not in (None, "SUCCESS") and "data" not in body:
                raise RuntimeError(f"KB API error: {body}")
            if attempt > 1:
                print(f"INFO: KB 조회 성공 ({attempt}번째 시도)")
            return body.get("data")
        except Exception as e:  # noqa: BLE001 - 창이 닫히면 마지막 예외를 올림
            last_err = e
            if _is_ssl_error(e):
                insecure = True  # 다음 시도부터 검증 완화 (사내 프록시 대응)
            remain = deadline - time.monotonic()
            if remain <= 0:
                break
            # 지터를 섞어 재시도가 한 박자로 몰리지 않게 한다
            nap = min(delay, BACKOFF_CAP_S, remain) * (0.7 + random.random() * 0.6)
            print(f"WARN: KB 조회 실패 {attempt}회 ({type(e).__name__}) — "
                  f"{nap:.1f}초 뒤 재시도 (남은 {remain:.0f}초)")
            time.sleep(max(0.1, nap))
            delay = min(delay * 2, BACKOFF_CAP_S)

    print(f"ERROR: KB 조회 {attempt}회 모두 실패 — {window_s}초 창을 소진했습니다")
    raise last_err


def region_list(code=""):
    """법정동코드 드릴다운. code 없으면 시/도, 2자리면 시/군/구, 5자리면 동 목록."""
    params = {"법정동코드": code} if code else {}
    return _get("/land-price/price/areaName", params) or []


def complex_list(dong_code):
    """법정동코드(10자리)의 아파트 단지 목록 → [{단지명, 단지기본일련번호, ...}]"""
    return _get("/land-complex/complexComm/hscmList", {"법정동코드": dong_code}) or []


def area_types(complex_id):
    """단지의 평형(면적) 목록 → [{면적일련번호, 공급면적평, 전용면적, ...}]"""
    return _get("/land-complex/complex/typInfo", {"단지기본일련번호": complex_id}) or []


def price_info(complex_id, area_id):
    """평형별 KB시세. 반환: dict(시세 배열 포함), 금액 단위 만원."""
    return _get(
        "/land-price/price/BasePrcInfoNew",
        {"단지기본일련번호": complex_id, "면적일련번호": area_id},
    )


def latest_price(complex_id, area_id, field="매매일반거래가"):
    """가장 최근 KB시세 1건에서 지정 필드(만원)와 기준일을 반환."""
    data = price_info(complex_id, area_id)
    rows = (data or {}).get("시세") or []
    if not rows:
        return None, None
    row = rows[0]
    date_keys = [k for k in row if "일자" in k or "기준" in k]
    base_date = str(row.get(date_keys[0])) if date_keys else ""
    if len(base_date) == 8 and base_date.isdigit():
        base_date = f"{base_date[:4]}-{base_date[4:6]}-{base_date[6:]}"
    return row.get(field), base_date
