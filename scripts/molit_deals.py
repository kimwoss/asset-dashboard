# -*- coding: utf-8 -*-
"""국토교통부 오피스텔 전월세 실거래가 — 후보 건물만 골라 온다.

호가(네이버)는 자동수집이 막혀 있지만 실거래는 국가가 신고받는 공적 정보라 공개 API가 있다.
'다음 후보집' 탭에서 호가 옆에 실제 계약가를 나란히 보여주는 데 쓴다.

의존성을 늘리지 않으려고 표준 라이브러리(urllib)만 쓴다.
키(MOLIT_API_KEY)가 없으면 빈 결과 — 탭은 그대로 뜨고 실거래 칸만 비운다.
"""
from __future__ import annotations

import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any, Dict, List, Optional

ENDPOINT = "https://apis.data.go.kr/1613000/RTMSDataSvcOffiRent/getRTMSDataSvcOffiRent"
KEY_ENVS = ("MOLIT_API_KEY", "DATA_GO_KR_KEY", "PUBLIC_DATA_API_KEY")

PYEONG = 3.305785
REGIONS = {"11560": "영등포구", "41290": "과천시"}

# ⚠️ 부분일치는 위험하다 — '아크로'는 '아크로타워'를, '파라곤'은 '문래파라곤'을 잡는다.
#    공백·동 접미사를 떼고 완전일치만 인정한다.
BUILDINGS = {
    # 시그니티·파라곤은 2026-08-19 후보에서 제외 — 조회할 필요가 없다.
    # 다시 넣으려면 여기와 officetel_sync.NAME_MAP 양쪽에 되살릴 것.
    "브라이튼여의도": "브라이튼",
    "아크로여의도더원": "아크로더원",
    "힐스테이트여의도파인루체": "힐스테이트 파인루체",
    "힐스테이트과천중앙": "힐스테이트과천중앙",
}
_DONG = re.compile(r"\d+동$")
# 전용면적 버킷 — 0.5평 단위로 묶어 같은 타입끼리 모은다
BUCKET_STEP = 0.5


def _key() -> Optional[str]:
    for n in KEY_ENVS:
        v = os.getenv(n)
        if v and v.strip():
            return v.strip()
    return None


def bucket_key(name: str, area_py: float) -> str:
    return f"{name}|{round(area_py / BUCKET_STEP) * BUCKET_STEP:g}"


def _match(raw: str) -> Optional[str]:
    return BUILDINGS.get(_DONG.sub("", raw.replace(" ", "")).strip())


def _txt(node: ET.Element, *names: str) -> str:
    for n in names:
        el = node.find(n)
        if el is not None and (el.text or "").strip():
            return el.text.strip()
    return ""


def _num(s: str) -> Optional[float]:
    s = re.sub(r"[^\d.\-]", "", s or "")
    try:
        return float(s)
    except ValueError:
        return None


def _fetch_month(lawd: str, ym: str, key: str) -> List[Dict[str, Any]]:
    q = urllib.parse.urlencode({
        "serviceKey": key, "LAWD_CD": lawd, "DEAL_YMD": ym,
        "numOfRows": 1000, "pageNo": 1,
    })
    try:
        with urllib.request.urlopen(f"{ENDPOINT}?{q}", timeout=30) as r:
            root = ET.fromstring(r.read().decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 실거래 조회 실패 ({lawd} {ym}): {e}")
        return []

    code = _txt(root, ".//resultCode", ".//returnReasonCode")
    if code and code not in ("00", "000"):
        print(f"WARN: 실거래 API 오류 {code}: {_txt(root, './/resultMsg', './/returnAuthMsg')[:100]}")
        return []

    out = []
    for it in root.findall(".//item"):
        name = _match(_txt(it, "offiNm", "aptNm"))
        if not name:
            continue
        area = _num(_txt(it, "excluUseAr"))
        dep = _num(_txt(it, "deposit"))
        mon = _num(_txt(it, "monthlyRent")) or 0
        if not (area and dep):
            continue
        y, m, d = _txt(it, "dealYear"), _txt(it, "dealMonth"), _txt(it, "dealDay")
        out.append({
            "name": name,
            "area": round(area / PYEONG, 2),
            "floor": _num(_txt(it, "floor")),
            "deposit": int(dep),
            "monthly": int(mon),
            # 시트·호가와 같은 환산식이라 두 값을 바로 견줄 수 있다
            "converted": int(dep + mon / 40 * 10_000),
            "date": f"{y}-{int(m):02d}-{int(d):02d}" if y and m and d else "",
        })
    return out


def fetch_deals(months: int = 12, today: Optional[date] = None) -> Dict[str, List[Dict]]:
    """{버킷키: [거래 …]} — 최신순. 키가 없으면 빈 dict."""
    key = _key()
    if not key:
        print(f"WARN: 공공데이터 키 없음 ({' / '.join(KEY_ENVS)}) — 실거래 생략")
        return {}

    today = today or date.today()
    rows: List[Dict] = []
    y, m = today.year, today.month
    for _ in range(months):
        for cd in REGIONS:
            rows += _fetch_month(cd, f"{y}{m:02d}", key)
        m -= 1
        if m == 0:
            y, m = y - 1, 12

    out: Dict[str, List[Dict]] = {}
    for r in rows:
        out.setdefault(bucket_key(r["name"], r["area"]), []).append(r)
    for v in out.values():
        v.sort(key=lambda x: x["date"], reverse=True)
        del v[24:]                      # 타입당 최근 24건이면 흐름 파악에 충분
    print(f"실거래 {len(rows)}건 / {len(out)}개 타입 버킷")
    return out
