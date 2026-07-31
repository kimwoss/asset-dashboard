# -*- coding: utf-8 -*-
"""아파트 단지ID/면적ID 대화형 조회 도구.

사용법: python tools/kb_lookup.py   (scripts/를 import 경로에 넣고 실행)
시/도 → 시/군/구 → 동 → 단지 → 평형 순으로 골라가면
portfolio.yaml에 넣을 complex_id / area_id를 출력합니다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import kb_api

sys.stdout.reconfigure(encoding="utf-8")


def pick(items, label_fn, title):
    print(f"\n=== {title} ===")
    for i, it in enumerate(items):
        print(f"{i + 1:3d}. {label_fn(it)}")
    while True:
        raw = input("번호 선택 (또는 이름 일부 입력): ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return items[int(raw) - 1]
        matches = [it for it in items if raw and raw in label_fn(it)]
        if len(matches) == 1:
            return matches[0]
        if matches:
            items = matches
            for i, it in enumerate(items):
                print(f"{i + 1:3d}. {label_fn(it)}")
        else:
            print("일치하는 항목이 없습니다.")


def region_name(r):
    return (r.get("소지역명") or r.get("중지역명") or r.get("대지역명") or "").strip()


def main():
    sido = pick(kb_api.region_list(), region_name, "시/도")
    gungu = pick(kb_api.region_list(sido["법정동코드"]), region_name, "시/군/구")
    dong = pick(kb_api.region_list(gungu["법정동코드"]), region_name, "읍/면/동")

    complexes = kb_api.complex_list(dong["법정동코드"])
    cx = pick(complexes, lambda c: c.get("단지명", ""), f"{region_name(dong)} 단지 ({len(complexes)}개)")
    cid = cx["단지기본일련번호"]

    types = kb_api.area_types(cid)
    typ = pick(
        types,
        lambda t: f"{t.get('공급면적평')}평 (전용 {t.get('전용면적')}㎡, 타입 {t.get('주택형타입내용') or '-'})",
        "평형",
    )
    aid = typ["면적일련번호"]

    price, base_date = kb_api.latest_price(cid, aid)
    print("\n" + "=" * 50)
    print(f"단지: {cx.get('단지명')} / {typ.get('공급면적평')}평")
    if price:
        print(f"현재 KB시세(매매일반거래가): {price / 10000:.2f}억 (기준일 {base_date})")
    print("\nportfolio.yaml에 아래를 추가하세요:")
    print(f"""
  - name: {cx.get('단지명')}
    owner: 남편   # 또는 아내
    complex_id: {cid}
    area_id: {aid}
    price_field: 매매일반거래가
    note: {typ.get('공급면적평')}평형
""")


if __name__ == "__main__":
    main()
