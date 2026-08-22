# -*- coding: utf-8 -*-
"""대시보드 배포 전 자동 점검. 레포 루트에서 실행한다.

눈으로 못 잡는 회귀만 본다 — 구문, 유출, 토큰 이탈, 접근성 골격, 성능 예산,
그리고 파이프라인 양끝(리더 ↔ 프런트)이 어긋났는지.
"""
from __future__ import annotations
import json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HTML = ROOT / "docs" / "index.html"
OK, FAIL, WARN = [], [], []


def ok(m): OK.append(m)
def bad(m): FAIL.append(m)
def warn(m): WARN.append(m)


def main() -> int:
    if not HTML.exists():
        print(f"index.html 없음: {HTML}"); return 2
    s = HTML.read_text(encoding="utf-8")
    js = "".join(m.group(1) for m in
                 re.finditer(r"<script(?![^>]*src=)[^>]*>(.*?)</script>", s, re.S))

    # ── 1. JS 구문 ─────────────────────────────────────────────────────────
    tmp = ROOT / ".dashboard-ship-check.js"
    try:
        tmp.write_text(js, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(tmp)], capture_output=True, text=True)
        ok("JS 구문") if r.returncode == 0 else bad(f"JS 구문: {r.stderr.strip()[:200]}")
    except FileNotFoundError:
        warn("node 없음 — JS 구문 검사 건너뜀")
    finally:
        tmp.unlink(missing_ok=True)

    # ── 2. 평문 금융데이터가 추적되는가 (가장 위험) ────────────────────────
    try:
        tracked = subprocess.run(["git", "ls-files"], cwd=ROOT,
                                 capture_output=True, text=True).stdout.split()
        leak = [f for f in tracked
                if re.search(r"(latest|live|history|portfolio)\.(json|csv|yaml)$", f)]
        ok("평문 금융데이터 미추적") if not leak else bad(f"평문이 추적됨: {leak}")
    except Exception as e:
        warn(f"git 확인 실패: {e}")

    # ── 3. 성능 예산 — 화면 폭별 1회 다운로드 ──────────────────────────────
    assets = ROOT / "docs" / "assets"
    budget = {"hero.webp": 650, "hero-md.webp": 400, "hero-sm.webp": 220}
    for name, kb in budget.items():
        p = assets / name
        if not p.exists():
            warn(f"{name} 없음"); continue
        got = p.stat().st_size / 1024
        (ok if got <= kb else bad)(f"{name} {got:.0f}KB (예산 {kb}KB)")

    # ── 4. head 필수 ───────────────────────────────────────────────────────
    need = {
        'name="description"': "description",
        'name="theme-color"': "theme-color",
        'rel="manifest"': "manifest",
        'rel="icon"': "favicon",
        "<noscript": "noscript",
        'lang="ko"': "lang",
    }
    miss = [label for probe, label in need.items() if probe not in s]
    ok("head 필수 태그") if not miss else bad(f"head 누락: {miss}")

    # ── 5. 접근성 골격 ─────────────────────────────────────────────────────
    tabs = s.count('class="tab"') + s.count('class="tab on"')
    roles = s.count('role="tab"')
    (ok if roles >= tabs else bad)(f'탭 role: {roles}/{tabs}')
    (ok if 'aria-live' in s else bad)("aria-live 존재")
    (ok if 'aria-selected' in js else bad)("전환 로직이 aria-selected를 갱신")

    # ── 6. 디자인 토큰 이탈 ────────────────────────────────────────────────
    css = "".join(m.group(1) for m in re.finditer(r"<style[^>]*>(.*?)</style>", s, re.S))
    decl = re.findall(r"--[a-z0-9-]+\s*:", css)
    hexes = re.findall(r"#[0-9a-fA-F]{6}\b", css)
    # 토큰 정의부의 hex는 정상. 그 밖에서 쓰이는 것만 센다.
    outside = len(hexes) - len(re.findall(r"--[a-z0-9-]+\s*:\s*#[0-9a-fA-F]{6}", css))
    (ok if outside <= 60 else warn)(f"토큰 밖 hex {outside}회 (토큰 {len(decl)}개)")

    # ── 7. 파이프라인 정합 — 리더 ↔ TTL ↔ applyLive ────────────────────────
    live = ROOT / "scripts" / "update_live.py"
    if live.exists():
        t = live.read_text(encoding="utf-8")
        block = re.search(r"TTL_MIN\s*=\s*\{(.*?)\}", t, re.S)
        keys = set(re.findall(r'"([a-z_]+)"\s*:', block.group(1))) if block else set()
        payload = set(re.findall(r'"([a-z_]+)"\s*:\s*[a-z_]+\s*or\s*None', t))
        orphan = {k for k in keys if k not in payload and k not in ("financial", "checkpoint", "baselines")}
        # applyLive 안에는 for-of 루프가 여러 개다(us/kr/fx 등). 하나만 보면 오탐이 나므로
        # 함수 전체에서 모든 루프의 키를 모아 합집합으로 본다.
        fn = re.search(r"function applyLive(.*?)\nfunction ", js, re.S)
        if fn:
            fk = set()
            for loop in re.findall(r"for \(const k of \[(.*?)\]\)", fn.group(1), re.S):
                fk |= set(re.findall(r'"([a-z_]+)"', loop))
            gap = {k for k in keys if k not in fk and k not in ("checkpoint", "baselines")}
            ok("applyLive가 모든 블록을 반영") if not gap else bad(f"applyLive 누락: {gap}")

    # ── 결과 ───────────────────────────────────────────────────────────────
    for m in OK:   print(f"  PASS  {m}")
    for m in WARN: print(f"  WARN  {m}")
    for m in FAIL: print(f"  FAIL  {m}")
    print(f"\n통과 {len(OK)} · 경고 {len(WARN)} · 실패 {len(FAIL)}")
    if FAIL:
        print("실패가 있으면 배포하지 않는다.")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
