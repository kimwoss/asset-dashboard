# -*- coding: utf-8 -*-
"""'오늘의 체크포인트' — 분당부부 모닝 리포트를 시트에서 읽어온다.

bundang-market-report(private)가 매일 07:00 리포트를 발송한 뒤
⭐️분당부부_MASTER '★오늘의체크포인트' 탭 A3에 JSON을 기록한다.
두 레포는 서로 접근 권한이 없어 시트가 중계 역할을 한다 — 추가 시크릿 불필요.

담긴 것: 뉴스 브리핑 · 운세 · 지수/환율/공포탐욕 · 매크로 D-day · 날씨
(순자산·FIRE는 애초에 보내지 않는다 — 다른 탭에 있고 public 레포로 나갈 이유가 없다)

실패는 파이프라인을 죽이지 않는다 — 예외 시 {} 반환, 대시보드는 해당 탭만 비운다.
"""
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

import sheets_fire  # 인증 재사용

SPREADSHEET_ID = sheets_fire.SPREADSHEET_ID
TAB = "★오늘의체크포인트"
PAYLOAD_CELL = "A3"
# 매일 나오는 리포트라 하루만 밀려도 이미 틀린 내용이다 — 특히 운세는 날짜 자체가
# 내용이라 어제 일진을 오늘 것으로 보여주면 거짓말이 된다. 종전엔 3일이라 2026-08-26에
# 워크플로가 통째로 유실됐는데도 화면은 어제 운세를 아무 표시 없이 보여줬다.
#
# 다만 '아직 오늘 걸 안 만든 이른 아침'과 '오늘 발송이 실패한 것'은 다르다.
# 모닝 리포트는 06~07시에 나오므로, 그 시각이 지나도 어제 것이면 그때 밀린 것으로 본다.
STALE_AFTER_HOUR = 8   # KST. 이 시각이 지났는데 어제 것이면 '밀렸다'
KST = timezone(timedelta(hours=9))


def fetch_checkpoint(today: Optional[date] = None) -> Dict[str, Any]:
    """★오늘의체크포인트 → 페이로드 dict. 실패/없음 시 {}."""
    today = today or date.today()
    try:
        import gspread
        gc = sheets_fire._authorize(gspread)
        if gc is None:
            print("WARN: 시트 인증정보 없음 — 체크포인트 생략")
            return {}
        ss = gc.open_by_key(SPREADSHEET_ID)
        try:
            ws = ss.worksheet(TAB)
        except gspread.exceptions.WorksheetNotFound:
            print(f"WARN: '{TAB}' 탭 없음 — 모닝 리포트가 아직 기록하지 않음")
            return {}
        blob = ws.acell(PAYLOAD_CELL).value
        if not blob or not blob.strip().startswith("{"):
            print("WARN: 체크포인트 페이로드 비어 있음")
            return {}
        payload = json.loads(blob)

        # 신선도 — 리포트가 며칠 밀렸는지 대시보드가 알 수 있게
        gen = payload.get("generated_at", "")
        try:
            gen_date = datetime.fromisoformat(gen).date()
            age = (today - gen_date).days
            payload["age_days"] = age
            # 이틀 이상이면 무조건, 하루면 발송 시각이 지난 뒤부터 밀린 것으로 본다
            payload["stale"] = age >= 2 or (
                age == 1 and datetime.now(KST).hour >= STALE_AFTER_HOUR)
        except (ValueError, TypeError):
            payload["age_days"] = None
            payload["stale"] = False

        print(f"OK: 체크포인트 {payload.get('date_label', '?')} "
              f"(뉴스 {len(payload.get('news', []))}건 · "
              f"운세 {'있음' if payload.get('fortune') else '없음'}"
              f"{' · ⚠️ ' + str(payload['age_days']) + '일 지남' if payload.get('stale') else ''})")
        return payload
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 체크포인트 읽기 실패 ({type(e).__name__}: {e}) — 탭 생략")
        return {}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    d = fetch_checkpoint()
    if d:
        print("\n키:", list(d.keys()))
        print("날씨:", d.get("weather", "")[:60])
        print("인사:", d.get("greeting", "")[:60])
        for n in d.get("news", []):
            print(" ·", n["title"][:50])
