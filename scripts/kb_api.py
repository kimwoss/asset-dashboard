# -*- coding: utf-8 -*-
"""KB부동산(kbland.kr) 비공식 API 클라이언트.

인증 불필요. 모든 금액 단위: 만원.
"""
import json
import time
import urllib.parse
import urllib.request

BASE = "https://api.kbland.kr"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://kbland.kr/",
    "Accept": "application/json",
}


def _get(path, params, retries=3):
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    last_err = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.load(resp)
            body = data.get("dataBody", {})
            if body.get("message") not in (None, "SUCCESS") and "data" not in body:
                raise RuntimeError(f"KB API error: {body}")
            return body.get("data")
        except Exception as e:  # noqa: BLE001 - 재시도 후 마지막 예외를 올림
            last_err = e
            time.sleep(2 * (i + 1))
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
