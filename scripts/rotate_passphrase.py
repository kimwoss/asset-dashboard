# -*- coding: utf-8 -*-
"""대시보드 비밀번호 바꾸기 — 커밋된 암호문 3개를 새 비밀번호로 다시 잠근다.

비밀번호는 화면에 표시하지 않고 입력받으며, 어디에도 저장하지 않는다.

    python scripts/rotate_passphrase.py

순서 (끝까지 이어서 할 것 — 사이가 벌어지면 그동안 실시간 갱신이 '못 받음'으로 보인다):
  1) 이 스크립트 실행 — 지금 비밀번호 확인 → 새 비밀번호 두 번 입력 → 3개 파일 재암호화
  2) git add / commit / push (스크립트가 마지막에 명령을 보여 준다)
  3) GitHub 시크릿 ASSET_PASSPHRASE를 같은 값으로 — 아래 둘 중 하나
       · gh secret set ASSET_PASSPHRASE -R kimwoss/asset-dashboard   (값을 숨김 입력)
       · GitHub → Settings → Secrets and variables → Actions → ASSET_PASSPHRASE → Update
  4) 폰·노트북에서 대시보드를 열면 "비밀번호가 바뀌었어요"가 뜬다 — 새 비밀번호를 한 번 입력

live-data 브랜치의 live.enc는 손대지 않는다. 시크릿을 바꾼 뒤 다음 실시간 잡(10분 안)이
새 비밀번호로 다시 굽는다. 그 잡은 직전 파일이 안 열리면 전체 갱신으로 넘어간다.
"""
import getpass
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import crypto_util  # noqa: E402

FILES = [ROOT / "config" / "portfolio.enc",
         ROOT / "docs" / "data" / "latest.enc",
         ROOT / "docs" / "data" / "history.enc"]
# 공개 저장소다 — 짧은 비밀번호는 파일을 받은 누구나 노트북으로 몇 분이면 푼다.
MIN_LEN = 12


def _opens(path: Path, pw: str) -> bool:
    with tempfile.TemporaryDirectory() as td:
        try:
            crypto_util.decrypt_file(path, Path(td) / "x", pw)
            return True
        except Exception:  # noqa: BLE001
            return False


def main() -> int:
    missing = [p for p in FILES if not p.exists()]
    if missing:
        print("파일이 없습니다:", ", ".join(str(p.relative_to(ROOT)) for p in missing))
        return 1

    cur = getpass.getpass("지금 비밀번호: ")
    if not all(_opens(p, cur) for p in FILES):
        print("지금 비밀번호로 열리지 않는 파일이 있습니다 — 아무것도 바꾸지 않았습니다.")
        return 1

    new = getpass.getpass("새 비밀번호: ")
    if getpass.getpass("새 비밀번호 한 번 더: ") != new:
        print("두 번 입력한 값이 다릅니다 — 아무것도 바꾸지 않았습니다.")
        return 1
    if new == cur:
        print("지금과 같은 비밀번호입니다 — 바꿀 것이 없습니다.")
        return 1
    if len(new) < MIN_LEN:
        print(f"⚠️ {len(new)}자입니다. 공개 저장소라 {MIN_LEN}자 미만이면 파일을 받은 사람이 "
              f"짧은 시간에 풀 수 있습니다. 낱말 서너 개를 이은 형태를 권합니다.")
        if input("그래도 이대로 쓰려면 '네'를 입력: ").strip() != "네":
            print("취소했습니다 — 아무것도 바꾸지 않았습니다.")
            return 1

    with tempfile.TemporaryDirectory() as td:     # 평문은 여기서만 잠깐 존재한다
        for p in FILES:
            plain = Path(td) / (p.name + ".plain")
            crypto_util.decrypt_file(p, plain, cur)
            tmp = p.with_suffix(".enc.new")
            crypto_util.encrypt_file(plain, tmp, new)
            if not _opens(tmp, new) or _opens(tmp, cur):
                tmp.unlink(missing_ok=True)
                print(f"{p.name} 검증 실패 — 원본은 그대로 두었습니다.")
                return 1
            os.replace(tmp, p)
            print(f"  다시 잠금: {p.relative_to(ROOT)}")

    print("\n다음 두 가지를 이어서 하세요:")
    print("  git add config/portfolio.enc docs/data/latest.enc docs/data/history.enc")
    print('  git commit -m "security: 비밀번호 교체" && git push')
    print("  gh secret set ASSET_PASSPHRASE -R kimwoss/asset-dashboard   ← 새 비밀번호를 숨김 입력")
    return 0


if __name__ == "__main__":
    sys.exit(main())
