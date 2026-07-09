# 우리집 자산 대시보드

부부 자산(아파트 KB시세 + 미국/한국 지수 ETF + 현금)을 자동 추적하는 대시보드.

- **아파트**: KB부동산 시세 (주 1회, 금요일 갱신)
- **증권**: yfinance 일일 종가 (미국 ETF는 USD/KRW 환율 자동 적용)
- **자동 갱신**: GitHub Actions — 매일 KST 06:20(미국 마감 후) / 평일 16:20(한국 마감 후)
- **대시보드**: `docs/index.html` (GitHub Pages, 비밀번호 입력 시 복호화)

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
| `docs/data/latest.enc` | 최신 스냅샷 (암호화, 대시보드 소스) |
| `docs/data/history.enc` | 자산별 일별 평가액 이력 (암호화, 자동 누적) |
| `config/portfolio.enc` | 보유내역 (암호화) |
