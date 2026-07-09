# 우리집 자산 대시보드

부부 자산(아파트 KB시세 + 미국/한국 지수 ETF + 현금)을 자동 추적하는 대시보드.

- **아파트**: KB부동산 시세 (주 1회, 금요일 갱신)
- **증권**: yfinance 일일 종가 (미국 ETF는 USD/KRW 환율 자동 적용)
- **자동 갱신**: GitHub Actions — 매일 KST 06:20(미국 마감 후) / 평일 16:20(한국 마감 후)
- **대시보드**: `docs/index.html` (GitHub Pages)

## 보유내역 수정

[config/portfolio.yaml](config/portfolio.yaml) 하나만 고치면 됩니다.
수량 변경, 종목 추가/삭제, 현금 잔액 갱신 모두 이 파일에서.
push하면 다음 자동 실행 때 반영. 즉시 반영하려면 Actions 탭에서
`update-asset-data` → Run workflow.

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
| `docs/data/latest.json` | 최신 스냅샷 (대시보드 소스) |
| `docs/data/history.csv` | 자산별 일별 평가액 이력 (자동 누적) |

주의: 이 레포에는 자산 정보가 들어가므로 **반드시 private**으로 유지할 것.
