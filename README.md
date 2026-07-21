# 분당부부 대시보드

부부 자산(아파트 KB시세 + 미국/한국 지수 ETF + 현금)을 자동 추적하는 대시보드.

- **아파트**: KB부동산 시세 (주 1회, 금요일 갱신)
- **증권**: yfinance 일일 종가 (미국 ETF는 USD/KRW 환율 자동 적용)
- **FIRE 목표**: ⭐️분당부부_MASTER `★종합` 탭에서 은퇴 목표·가정치 연동 (달성률은 실시간 순자산으로 재계산)
- **자동 갱신**: GitHub Actions — 매일 KST 06:20(미국 마감 후) / 평일 16:20(한국 마감 후)
- **대시보드**: `docs/index.html` (GitHub Pages, 비밀번호 입력 시 복호화)

## FIRE 목표 연동 (★종합 시트)

대시보드 상단에 은퇴 목표 달성 현황을 표시한다. 자산 평가(KB/yfinance)는 대시보드가
실시간 계산하고, `★종합` 탭에서는 **목표·가정치만** 읽어와 조화시킨다:

- 시트에서: 목표금액(기본/부자), 목표연도, 은퇴 후 월생활비, 자산 소진 나이, 세후 실질수익률
- 달성률: 시트의 % 대신 **대시보드 실시간 순자산 ÷ 목표금액**으로 재계산 (표시 순자산과 항상 일치)
- 읽기 인증: GitHub Secret **`GOOGLE_SHEETS_CREDENTIALS`** (서비스계정 JSON) 필요
  - 서비스계정이 ⭐️분당부부_MASTER에 '뷰어'로 공유돼 있어야 함 (bundang-market-report와 동일 계정 재사용 가능)
  - **미설정 시 FIRE 섹션만 자동 생략** — 자산 추적 핵심 기능은 영향 없음
- 로컬 테스트: `GOOGLE_SHEETS_CREDENTIALS_FILE=경로/credentials.json` 또는 `config/credentials.json`(gitignore)

## 보안 구조 (공개 레포)

민감한 파일은 AES-256-GCM으로 암호화된 `.enc`만 커밋됩니다.
평문(`portfolio.yaml`, `latest.json`, `history.csv`)은 gitignore.

- 비밀번호는 GitHub Actions Secret `ASSET_PASSPHRASE`에 저장
- 대시보드는 접속 시 같은 비밀번호를 입력하면 브라우저에서 복호화 (기기에 저장됨)
- 비밀번호 변경: Settings → Secrets → `ASSET_PASSPHRASE` 수정 후,
  로컬에서 새 비밀번호로 `.enc` 3개를 재암호화해 커밋

## 보유내역 수정

로컬의 `config/portfolio.yaml`(gitignore됨)을 고친 뒤:

```bash
set ASSET_PASSPHRASE=비밀번호        # PowerShell: $env:ASSET_PASSPHRASE="비밀번호"
python scripts/run_ci.py            # 갱신 + 재암호화
git add -A && git commit -m "update" && git push
```

`portfolio.yaml`이 없으면 `python scripts/crypto_util.py decrypt config/portfolio.enc config/portfolio.yaml`로 복원.

## 아파트 단지ID 찾기

```bash
python scripts/kb_lookup.py
```

시/도 → 구 → 동 → 단지 → 평형 순으로 고르면 `portfolio.yaml`에
붙여넣을 블록을 출력해 줍니다.

## 로컬 실행

```bash
pip install -r requirements.txt
python scripts/update_data.py        # 데이터 갱신
python -m http.server -d docs 8788   # http://localhost:8788 에서 대시보드 확인
```

## 데이터 파일

| 파일 | 내용 |
|---|---|
| `docs/data/latest.enc` | 최신 스냅샷 + FIRE 목표 블록 (암호화, 대시보드 소스) |
| `docs/data/history.enc` | 자산별 일별 평가액 이력 (암호화, 자동 누적) |
| `config/portfolio.enc` | 보유내역 (암호화) |
| `scripts/sheets_fire.py` | ★종합 탭 FIRE 결과 요약 읽기 (읽기 전용, 실패 시 그레이스풀) |
