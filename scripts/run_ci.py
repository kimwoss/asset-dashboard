# -*- coding: utf-8 -*-
"""CI/로컬 공용 실행기: 복호화 → 데이터 갱신 → 재암호화.

레포에는 암호화된 파일만 존재한다:
  config/portfolio.enc, docs/data/latest.enc, docs/data/history.enc
평문(portfolio.yaml, latest.json, history.csv)은 gitignore 대상.

동작:
  1. portfolio.yaml 없으면 portfolio.enc에서 복호화
  2. history.csv 없으면 history.enc에서 복호화 (이력 이어쓰기용)
  3. update_data.main() 실행
  4. 산출물을 .enc로 암호화
  5. CI(GITHUB_ACTIONS)에서는 평문 삭제
"""
import os
import sys
from pathlib import Path

import crypto_util
import update_data

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "docs" / "data"


def main():
    pw = crypto_util.get_passphrase()
    in_ci = os.environ.get("GITHUB_ACTIONS") == "true"

    if not (CONFIG / "portfolio.yaml").exists():
        crypto_util.decrypt_file(CONFIG / "portfolio.enc", CONFIG / "portfolio.yaml", pw)
        print("portfolio.enc 복호화")
    if not (DATA / "history.csv").exists() and (DATA / "history.enc").exists():
        crypto_util.decrypt_file(DATA / "history.enc", DATA / "history.csv", pw)
        print("history.enc 복호화")
    # 직전 스냅샷 — KB시세가 일시적으로 죽었을 때 그 값을 그대로 들고 가기 위한 폴백 원본이자,
    # 총자산 급감 감지의 기준값. 없으면 폴백 없이 진행한다(최초 실행).
    if not (DATA / "latest.json").exists() and (DATA / "latest.enc").exists():
        crypto_util.decrypt_file(DATA / "latest.enc", DATA / "latest.json", pw)
        print("latest.enc 복호화 (직전 스냅샷 폴백용)")

    update_data.main()

    crypto_util.encrypt_file(CONFIG / "portfolio.yaml", CONFIG / "portfolio.enc", pw)
    crypto_util.encrypt_file(DATA / "latest.json", DATA / "latest.enc", pw)
    crypto_util.encrypt_file(DATA / "history.csv", DATA / "history.enc", pw)
    print("암호화 완료: portfolio.enc, latest.enc, history.enc")

    if in_ci:
        for p in [CONFIG / "portfolio.yaml", DATA / "latest.json", DATA / "history.csv"]:
            p.unlink(missing_ok=True)
        print("CI: 평문 삭제")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
