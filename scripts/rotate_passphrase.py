# -*- coding: utf-8 -*-
"""대시보드 비밀번호 바꾸기 — 커밋된 암호문 3개를 새 비밀번호로 다시 잠근다.

비밀번호는 화면에 표시하지 않고 입력받으며, 어디에도 저장하지 않는다.

가장 간단한 길 (새 비밀번호만 두 번 치면 끝):

    python scripts/rotate_passphrase.py --current-file <지금 비밀번호가 든 파일> --push

  · --current-file  지금 비밀번호를 파일에서 읽는다(입력 생략). 끝까지 성공하면 그 파일은
                    지운다 — 옛 비밀번호는 더는 아무것도 열지 못하니 남길 이유가 없다.
  · --push          재암호화한 3개 파일을 커밋·푸시하고, GitHub 시크릿 ASSET_PASSPHRASE도
                    같은 값으로 바꾼다(gh CLI). 둘을 붙여서 해야 실시간 잡이 어긋나지 않는다.

옵션 없이 실행하면 지금 비밀번호도 묻고, 커밋·푸시·시크릿은 직접 하도록 명령만 보여 준다.

끝나면 폰·노트북에서 대시보드를 열 때 "비밀번호가 바뀌었어요"가 뜬다 — 새 비밀번호를 한 번 입력.
live-data 브랜치의 live.enc는 손대지 않는다. 시크릿을 바꾼 뒤 다음 실시간 잡(10~30분 안)이
새 비밀번호로 다시 굽는다. 그 잡은 직전 파일이 안 열리면 전체 갱신으로 넘어간다.
"""
import argparse
import getpass
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import crypto_util  # noqa: E402

REPO = "kimwoss/asset-dashboard"
FILES = [ROOT / "config" / "portfolio.enc",
         ROOT / "docs" / "data" / "latest.enc",
         ROOT / "docs" / "data" / "history.enc"]
REL = [str(p.relative_to(ROOT)).replace("\\", "/") for p in FILES]
# 공개 저장소다 — 짧은 비밀번호는 파일을 받은 누구나 노트북으로 몇 분이면 푼다.
MIN_LEN = 12


def _opens(path: Path, pw: str) -> bool:
    with tempfile.TemporaryDirectory() as td:
        try:
            crypto_util.decrypt_file(path, Path(td) / "x", pw)
            return True
        except Exception:  # noqa: BLE001
            return False


def _git(*args, check=True):
    # Windows 기본 코드페이지(cp949)로 읽으면 한글 커밋 메시지에서 디코딩이 터진다 —
    # 커밋 직후·시크릿 교체 직전에 멈추면 사이트와 시크릿이 어긋난 채 남는다.
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=check)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="대시보드 비밀번호 바꾸기")
    ap.add_argument("--current-file", help="지금 비밀번호가 든 파일 (입력 생략, 성공하면 삭제)")
    ap.add_argument("--push", action="store_true", help="커밋·푸시하고 GitHub 시크릿까지 바꾼다")
    a = ap.parse_args(argv)

    missing = [p for p in FILES if not p.exists()]
    if missing:
        print("파일이 없습니다:", ", ".join(str(p.relative_to(ROOT)) for p in missing))
        return 1

    if a.push:
        # 다른 노트북·자동 잡이 올린 최신본 위에서 바꿔야 푸시가 거절되지 않는다
        if _git("status", "--porcelain", "--", *REL).stdout.strip():
            print("암호문 파일에 커밋하지 않은 변경이 있습니다 — 정리한 뒤 다시 실행하세요.")
            return 1
        r = _git("pull", "--rebase", "origin", "main", check=False)
        if r.returncode != 0:
            print("최신본을 받지 못했습니다 — 아무것도 바꾸지 않았습니다.\n" + r.stderr.strip())
            return 1

    if a.current_file:
        cur_path = Path(a.current_file)
        cur = cur_path.read_text(encoding="utf-8").strip()
        print("지금 비밀번호: 파일에서 읽음")
    else:
        cur_path = None
        cur = getpass.getpass("지금 비밀번호: ")
    if not all(_opens(p, cur) for p in FILES):
        print("지금 비밀번호로 열리지 않는 파일이 있습니다 — 아무것도 바꾸지 않았습니다.")
        return 1

    print("\n새 비밀번호를 입력하세요. 치는 동안 화면에 아무것도 보이지 않는 게 정상입니다.")
    new = getpass.getpass("새 비밀번호: ")
    if getpass.getpass("새 비밀번호 한 번 더: ") != new:
        print("두 번 입력한 값이 다릅니다 — 아무것도 바꾸지 않았습니다.")
        return 1
    if not new.strip():
        print("비어 있습니다 — 아무것도 바꾸지 않았습니다.")
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

    if not a.push:
        print("\n다음을 이어서 하세요:")
        print("  git add " + " ".join(REL))
        print('  git commit -m "security: 비밀번호 교체" && git push')
        print(f"  gh secret set ASSET_PASSPHRASE -R {REPO}   ← 새 비밀번호를 숨김 입력")
        return 0

    # 커밋·푸시 → 곧바로 시크릿. 둘 사이가 벌어지면 그동안 실시간 잡이 옛 시크릿으로 돈다.
    _git("add", *REL)
    _git("commit", "-q", "-m", "security: 비밀번호 교체 (사용자 지정)")
    r = _git("push", "-q", "origin", "main", check=False)
    if r.returncode != 0:
        print("\n⚠️ 푸시 실패 — 커밋은 로컬에 있습니다. 'git pull --rebase && git push' 후 "
              f"'gh secret set ASSET_PASSPHRASE -R {REPO}'를 실행하세요.\n" + r.stderr.strip())
        return 1
    print("  푸시 완료")
    # 값은 표준입력으로만 넘긴다 — 명령줄 인자에 두면 프로세스 목록에 보인다
    # UTF-8로 넘긴다 — 브라우저(TextEncoder)와 crypto_util이 비밀번호를 UTF-8 바이트로 쓰므로,
    # 한글이 섞인 비밀번호를 cp949로 보내면 시크릿만 다른 값이 된다.
    r = subprocess.run(["gh", "secret", "set", "ASSET_PASSPHRASE", "-R", REPO],
                       input=new, text=True, encoding="utf-8", capture_output=True)
    if r.returncode != 0:
        print("\n⚠️ 시크릿 교체 실패 — 직접 실행하세요: "
              f"gh secret set ASSET_PASSPHRASE -R {REPO}\n" + r.stderr.strip())
        return 1
    print("  GitHub 시크릿 ASSET_PASSPHRASE 교체 완료")

    if cur_path:
        try:
            cur_path.unlink()
            print(f"  옛 비밀번호 파일 삭제: {cur_path}")
        except OSError as e:
            print(f"  ⚠️ 옛 비밀번호 파일을 지우지 못했습니다 — 직접 지워 주세요 ({e})")

    print("\n끝났습니다. 폰·노트북에서 대시보드를 열면 '비밀번호가 바뀌었어요'가 뜹니다 — "
          "새 비밀번호를 한 번 입력하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
