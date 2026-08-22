# 올리브영 신상품 히트 예측

> 출시 후 첫 2주의 리뷰·평점 데이터만으로 3개월 후 카테고리 베스트셀러 여부를 예측하는 프로젝트

📊 **포트폴리오 상세 (분석 스토리·인사이트)**: [Notion 프로젝트 페이지](https://gyumin-kim.notion.site/eebf07a35f5182dfaf8e0105c64a2976)

## 문제 정의

올리브영에서는 매월 수십 개의 신상품이 출시되지만, 그중 일부만 카테고리 상위에 안착합니다. 이 프로젝트는 **출시 직후 초기 시그널**(리뷰 속도, 별점 분산, 텍스트 토픽 등)만으로 장기 히트 여부를 조기 판별하는 분석·모델링을 수행합니다.

## 데이터

- **출처**: 올리브영 (직접 크롤링, 2026-04-27 기준)
- **범위**: 스킨케어·색조 메이크업 카테고리 베스트셀러 Top 100 × 2카테고리
- **수집 도구**: Playwright 기반 3계층 크롤러 (랭킹 → 상품 상세 → 리뷰)
- **저장·분석**: SQLite 원본 적재 + DuckDB JOIN·윈도우 함수·QUALIFY 피처 쿼리

| 테이블 | 행 수 | 설명 |
|---|---|---|
| `products` | 200개 | 상품 메타데이터 (이름·브랜드·가격·평점 등) |
| `rankings` | 200개 | 카테고리별 랭킹 스냅샷 |
| `reviews` | 18,695건 | 상품당 평균 93건, 2022~2026년 |

## 프로젝트 구조

```
oliveyoung-hit-prediction/
├── data/
│   ├── raw/          # 크롤링 원본 (SQLite, CSV) — git 미커밋
│   ├── interim/      # 중간 정제 데이터
│   └── processed/    # 모델 입력용 피처 테이블
├── notebooks/        # 탐색·실험 (사고 흐름 기록)
│   ├── 01_eda.ipynb
│   ├── 02_features.ipynb
│   └── 03_modeling.ipynb
├── src/              # 재사용 가능한 모듈
│   ├── crawler/      # ranking / product / review
│   ├── db/           # 스키마 정의
│   └── features/     # 피처 빌더
├── reports/
│   └── figures/      # 분석 시각화
└── tests/
```

## 환경 세팅

```bash
# 의존성 설치 (Python 3.12 자동 다운로드 + .venv 생성)
uv sync

# Playwright 브라우저 설치 (크롤링용)
uv run playwright install chromium

# Jupyter 실행
uv run jupyter lab
```

## 분석 접근

| 단계 | 내용 | 산출물 |
|---|---|---|
| 데이터 수집 | 카테고리 랭킹 + 상품 상세 + 리뷰 크롤링 | SQLite DB |
| EDA | 가격·평점·리뷰 수 분포, 카테고리별 차이 | `01_eda.ipynb` |
| 피처 엔지니어링 | 리뷰 속도, 별점 드리프트, 텍스트 토픽 등 | `product_features` 테이블 |
| 베이스라인 모델 | 로지스틱 회귀, 피처 중요도 해석 | `03_modeling.ipynb` |
| 텍스트 분석 | BERTopic 토픽 모델링, 감성 분석 | 추가 피처 |
| 결과 정리 | 시각화·블로그 포스팅·발표 자료 | `reports/` |

## 진행 상황

- [x] **1주차** — 크롤러 설계·구현, 초기 데이터 수집 ✅
  - Playwright 3계층 크롤러 구현 (ranking / product / review)
  - 200개 상품 · 18,695건 리뷰 수집 완료
  - IP Rate Limit 대응 (0건 감지 → 60초 대기 + 세션 교체 재시도)
- [x] **2주차** — EDA·데이터 정제 ✅
  - 라벨 정책 확정: `is_hit = (rank ≤ 30)`, 31~70위 제외
  - 분석 표본 119개 (히트 60 / 논히트 59)
- [x] **3주차** — 피처 엔지니어링 ✅
  - 리뷰 속도·별점 분산·드리프트 등 16피처 생성, evangelist 가설 정립
- [x] **4주차** — 베이스라인 모델 ✅
  - 로지스틱 회귀 ROC-AUC **0.5417** (의도적으로 약한 베이스라인), 핵심 신호 검증
- [x] **5주차** — 텍스트 분석 (BERTopic·감성) ✅
  - 카테고리별 토픽 모델링, 행동 지표와 같은 데이터에서 evangelist 가설을 다른 관점으로 교차 확인, 텍스트 피처 5개 추가
- [x] **6주차** — 모델 고도화·해석 (SHAP) ✅
  - 단일 80/20 분할에서 LightGBM + 텍스트 피처 AUC 0.6042를 관측했으나 반복 교차검증에서 재현되지 않아 대표 성능으로 사용하지 않음
- [x] **7주차** — 결과 정리·시각화 ✅
  - RepeatedStratifiedKFold(5×20)에서 구조 피처 LightGBM CV 평균 AUC 0.5883, 텍스트 포함 모델 0.5558
  - OOF 에러 분석으로 두 약점 그룹(조용한 만점형 / 분산형)을 재확인
- [x] **8주차** — 검증 결과와 현업 적용 한계 정리 ✅
  - [`reports/validation_results.md`](reports/validation_results.md): 단일 분할 결과의 재검증과 처방 실험
  - [`reports/md_review_rules.md`](reports/md_review_rules.md): 자동 판정이 아닌 MD 수동 검토 규칙 제안

## 작성자

김규민 — <rlarbals1230@naver.com>

## 라이선스 / 주의사항

본 프로젝트는 학습 및 포트폴리오 목적의 분석이며, 크롤링 데이터는 비공개로 보관합니다. 올리브영 robots.txt 정책 및 적정 요청 간격을 준수합니다.
