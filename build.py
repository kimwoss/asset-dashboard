# -*- coding: utf-8 -*-
"""src/ → docs/index.html 조립.

왜 나눠 두고 다시 합치나. 배포본은 반드시 한 파일이어야 한다 — CSS·JS를 따로 두면
요청이 늘고, 이 페이지의 '외부 요청 0개'는 첫 화면 속도의 근거다. 그래서 **소스만
나누고 산출은 그대로 한 파일**로 굽는다.

  src/index.template.html   @@STYLES@@ · @@APP@@ 두 자리만 표식
  src/styles.css            <style> 안에 들어갈 내용
  src/js/*.js               파일 이름 순으로 이어 붙는다 (순서가 곧 실행 순서)

JS 모듈을 더할 때는 **번호를 붙여 순서를 정한다**. 최상위 const는 호이스팅되지 않아
순서가 바뀌면 조용히 깨진다.

사용:
  python build.py            조립하고 바뀌었으면 쓴다
  python build.py --check    쓰지 않고 docs/index.html과 같은지만 본다 (CI·배포 점검용)
"""
from __future__ import annotations
import argparse, io, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC, OUT = ROOT / "src", ROOT / "docs" / "index.html"


def read(p: Path) -> str:
    return io.open(p, encoding="utf-8", newline="").read()


def build() -> str:
    tpl = read(SRC / "index.template.html")
    css = read(SRC / "styles.css")
    mods = sorted((SRC / "js").glob("*.js"))
    if not mods:
        sys.exit("src/js 에 모듈이 없다")
    app = "".join(read(m) for m in mods)
    if "@@STYLES@@" not in tpl or "@@APP@@" not in tpl:
        sys.exit("템플릿에 @@STYLES@@ / @@APP@@ 표식이 없다")
    return tpl.replace("@@STYLES@@", css).replace("@@APP@@", app)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="쓰지 않고 docs/index.html과 일치하는지만 확인")
    a = ap.parse_args()

    built = build()
    cur = read(OUT) if OUT.exists() else None
    mods = sorted((SRC / "js").glob("*.js"))
    print(f"모듈 {len(mods)}개 · {len(built):,}자")

    if built == cur:
        print("docs/index.html 과 일치")
        return 0
    if a.check:
        # 어디서 갈렸는지 알려 준다 — 손으로 docs를 고치면 여기서 걸린다
        n = min(len(built), len(cur or ""))
        i = next((k for k in range(n) if built[k] != cur[k]), n)
        print(f"FAIL: 불일치 — 첫 차이 {i:,}번째 글자 "
              f"({(cur or '')[:i].count(chr(10)) + 1}행 근처)")
        print("  docs/index.html 을 직접 고쳤다면 src/ 로 옮기고 다시 빌드할 것.")
        return 1
    OUT.write_text(built, encoding="utf-8", newline="")
    print(f"docs/index.html 갱신 ({len(cur or ''):,} → {len(built):,}자)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
