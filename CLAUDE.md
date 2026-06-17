# CLAUDE.md

이 파일은 Claude Code가 프로젝트 컨텍스트를 빠르게 잡기 위한 인수인계서입니다.
프로젝트 루트에서 매 세션 자동 로드됩니다.

---

## 프로젝트 한 줄 요약

**올리브영 신상품 히트 예측** — 출시 후 첫 2주의 리뷰·평점 데이터만으로 3개월 후 카테고리 베스트셀러 여부를 예측하는 **이진 분류** 프로젝트.

> ⚠️ "수요 예측"이 아닙니다. 판매량 회귀가 아니라 **히트/논히트 분류**예요. 면접 등에서 용어 혼동 주의.

## 작성자 / 협업 컨텍스트

- 김규민 (rlarbals1210@gmail.com)
- **데이터 분석가 취업 준비 중** (이커머스·커머스·유통 도메인 목표)
- **모델링 입문자**: 머신러닝 깊은 지식 없음 → 분석 중심 접근, 모델은 단순한 것부터 (로지스틱 회귀 → LightGBM 순)
- **한국어로 응답** 원함 (코드 내 변수명·주석은 영문 OK)
- **이해를 우선**: 코드보다 "왜 이렇게 하는지" 먼저 설명. 결정 시 옵션 A/B/C 비교 선호.

## 프로젝트 정의

### 핵심 가설
출시 직후 **초기 시그널** (리뷰 속도, 별점 분산, 별점 드리프트, 텍스트 토픽)만으로도 장기 히트 여부를 예측 가능하다.

### 레이블링 전략 — **소급 레이블링 (retroactive)**
3개월 기다리지 않기 위해 다음 두 집단을 동시 수집:
- **Positive (히트)**: 현재 카테고리 Top 50 안에 있는 상품
- **Negative (논히트)**: 3개월 전쯤 출시됐는데 지금 순위에 없거나 낮은 상품

→ 이 설계 덕분에 1주차에 데이터 수집 → 8주차에 모델 완성이 가능.

### 데이터 스코프 (의식적으로 좁게)
- **2~3개 카테고리만**: 스킨케어, 색조 메이크업 (필요시 헤어 추가)
- **상품 수**: 500~1,500개
- 전 카테고리 크롤링은 **하지 않음** — 카테고리별 히트 요인이 달라 모델 뭉개짐, 데이터 편차 심함, 차단 위험 ↑
- 포트폴리오 어필은 "넓게" 보다 **"좁고 깊게"**가 강함

### 작성자 인구통계는 의존하지 않음
올리브영 리뷰에서 작성자 프로필(연령·피부타입)은 **일부에만 존재**. 따라서 피처 엔지니어링은 **리뷰의 시간·텍스트·별점 패턴 자체**에 집중:

- ✅ 사용: 리뷰 속도, 별점 분산, 별점 드리프트, 포토 리뷰 비율, 리뷰 길이, 텍스트 토픽, 감성 점수
- ⚠️ 보조: 피부타입 태그 (있을 때만, NULL 허용)
- ❌ 의존하지 않음: 연령대 (대부분 없음 + 뷰티 카테고리는 변별력 낮음)

## 기술 스택과 선택 이유

| 영역 | 선택 | 이유 |
|---|---|---|
| Python | 3.12 | uv가 자동 관리 |
| 환경관리 | **uv** | 모던, pip보다 빠름, 포트폴리오 어필에도 유리 |
| 크롤링 | **Playwright** | 올영은 JS 렌더링 기반 → requests로 안 됨 |
| Raw DB | **SQLite** | 파일 하나, 휴대성, 재현 쉬움 |
| 분석 쿼리 | **DuckDB** | SQLite 파일 ATTACH해서 사용. PostgreSQL·BigQuery에 가까운 분석 SQL 문법 (윈도우 함수, QUALIFY, PIVOT). 포트폴리오 어필력 ↑ |
| 시각화 | matplotlib + seaborn | 표준 |
| 모델링 | scikit-learn | 1~4주차 베이스라인용. LightGBM은 6주차쯤 |
| 텍스트 | BERTopic, Okt/Kiwi | 5주차 |

> SQL 어필을 위해 **분석 쿼리는 DuckDB로 작성**. 포트폴리오 후반엔 핵심 쿼리 2~3개를 PostgreSQL 버전으로도 작성해 README에 첨부 예정.

## 프로젝트 구조

```
oliveyoung-hit-prediction/
├── data/
│   ├── raw/          # 크롤링 원본 (SQLite, CSV) — git 미커밋
│   ├── interim/      # 중간 정제
│   └── processed/    # 모델 입력용 피처 테이블
├── notebooks/        # 탐색·실험 (사고 흐름 기록 — 포트폴리오 핵심 자산)
│   ├── 01_eda.ipynb
│   ├── 02_features.ipynb
│   └── 03_modeling.ipynb
├── src/              # 재사용 가능한 모듈
│   ├── crawler/
│   │   ├── ranking.py      # 1층: 카테고리 랭킹 ✅ 구현 완료
│   │   ├── product.py      # 2층: 상품 상세   ✅ 구현 완료
│   │   └── review.py       # 3층: 리뷰         ✅ 구현 완료 (Rate Limit 재시도 포함)
│   ├── db/
│   │   └── schema.py       # SQLite 3-테이블 스키마 ✅ 구현 완료
│   └── features/
│       └── build_features.py  # 3주차 이후 구현
├── reports/figures/
└── tests/
```

### 파일 분리 원칙
- **`notebooks/`** = 탐색용. 분석가의 사고 과정을 그대로 남기는 곳. 면접관이 가장 먼저 봄.
- **`src/`** = 재사용용. 노트북에서 검증된 로직을 함수로 정리한 깨끗한 코드. "코드 깔끔하게 짤 줄 안다" 신호.
- 입문 단계엔 노트북에 다 넣어도 OK. 3주차쯤 안정되면 `src/`로 리팩토링 (학습 효과 큼).

## 데이터 스키마

### `products` (상품 마스터, 1상품 = 1행)
`product_id` PK, name, brand, category_main, category_sub, price, price_original, launch_date_est, review_count_total, rating_avg, url, crawled_at

### `rankings` (랭킹 스냅샷, 시계열)
snapshot_id PK, product_id FK, category, rank, snapshot_date
- 인덱스: `(product_id, snapshot_date)`, `(category, snapshot_date, rank)`

### `reviews` (리뷰 원본, 가장 큰 테이블)
review_id PK, product_id FK, rating, content, written_at, helpful_count, has_photo, author_id_masked, author_skin_type (nullable), crawled_at
- 인덱스: `product_id`, `written_at`

### `product_features` (파생, 분석 단계에서 생성)
3주차에 raw 3테이블에서 집계해 만듦. 모델의 직접 입력. 핵심 컬럼:
`reviews_2wk_count`, `reviews_2wk_velocity_slope`, `rating_2wk_mean`, `rating_2wk_std`, `rating_drift`, `photo_review_ratio_2wk`, `review_length_mean_2wk`, `topic_dominant`, `sentiment_score_mean`, **`is_hit`** (레이블)

## 8주차 로드맵

| 주차 | 핵심 작업 | 산출물 |
|---|---|---|
| **1** | 크롤러 설계·구현, 초기 데이터 수집 | SQLite DB |
| **2** | EDA, 데이터 정제 | `01_eda.ipynb` |
| **3** | 피처 엔지니어링 | `product_features` 테이블 |
| **4** | 베이스라인 모델 (로지스틱 회귀) | `03_modeling.ipynb` |
| **5** | 텍스트 분석 (BERTopic, 감성) | 추가 피처 |
| **6** | 모델 고도화 (LightGBM), SHAP 해석 | 모델 비교 표 |
| **7** | 결과 정리, 시각화 | `reports/` |
| **8** | 블로그 포스팅, 발표 자료 | 외부 산출물 |

## 자주 쓸 명령어

```bash
# 의존성 설치 / 동기화
uv sync

# Playwright 브라우저 (1회)
uv run playwright install chromium

# DB 초기화
uv run python -m src.db.schema --db data/raw/oliveyoung.db

# Jupyter
uv run jupyter lab

# 크롤러 실행
uv run python -m src.crawler.ranking --category skincare --save --db data/raw/oliveyoung.db
uv run python -m src.crawler.ranking --category makeup   --save --db data/raw/oliveyoung.db
uv run python -m src.crawler.product --db data/raw/oliveyoung.db --save
uv run python -m src.crawler.review  --db data/raw/oliveyoung.db --max-reviews 200 --save

# launch_date_est 업데이트 (리뷰 수집 후 1회)
uv run python -c "from src.crawler.review import update_launch_dates; update_launch_dates('data/raw/oliveyoung.db')"
```

## 작성·커뮤니케이션 원칙

- **결정에는 trade-off 명시**: "A로 하면 X 좋고 Y 약함. B로 하면 반대" 형식 선호
- **포트폴리오 어필 관점 항상 고려**: 기술적 정답보다 "이게 면접에서 어떻게 보일까"를 함께 따짐
- **모델보다 분석 우선**: 모델 정확도 0.85 → 0.87 보다, "이 분석으로 어떤 의사결정이 바뀌는가"가 더 중요
- **모르는 건 모른다고 말하기**: 추측을 단정처럼 말하지 않기. 작성자 정보 같은 것은 실제 페이지 확인 후 답하기

## 세션 관리 규칙

### 토큰 90% 도달 시 의무 행동
작업 도중 토큰 사용량이 90% 이상이 되면 반드시:
1. 현재 작업 중인 코드를 저장 가능한 상태로 마무리 (미완성이면 `# TODO: 여기서 중단` 주석 추가)
2. 아래 **현재 상태** 섹션을 업데이트:
   - ✅ 완료한 항목 추가
   - ⏳ 다음에 이어서 할 작업을 구체적으로 기술 (파일명, 함수명, 어느 부분부터인지)
3. **다음 세션 추천 시작 멘트** 섹션을 현재 맥락으로 업데이트
4. 사용자에게 "토큰 한도 근접으로 세션을 마무리합니다. CLAUDE.md를 업데이트했습니다." 고지

### Notion 포트폴리오 동기화 (클로드 데스크탑 활용)
코드·분석에 의미있는 진전이 생기면 클로드 데스크탑 + Notion MCP로 포트폴리오를 업데이트한다.

**Notion MCP 설정 방법** (최초 1회):
1. Notion에서 Integration 생성 → API 키 발급
   - <https://www.notion.so/profile/integrations>
2. 업데이트할 페이지에 Integration 연결 (페이지 우상단 ··· → Connections)
3. Claude Desktop `~/Library/Application Support/Claude/claude_desktop_config.json`에 추가:
```json
{
  "mcpServers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "OPENAPI_MCP_HEADERS": "{\"Authorization\": \"Bearer YOUR_NOTION_API_KEY\", \"Notion-Version\": \"2022-06-28\"}"
      }
    }
  }
}
```
4. Claude Desktop 재시작 → 좌하단 MCP 아이콘에 notion 표시 확인

**동기화 트리거 시점** (이 중 하나 해당하면):
- 새 크롤러 함수 완성 & 실제 데이터 수집 성공
- EDA 노트북에 인사이트 추가
- 모델 베이스라인 결과 나왔을 때
- 주차별 마일스톤 완료

**클로드 데스크탑에 할 말 템플릿**:
> "올영 프로젝트 Notion 페이지(<https://www.notion.so/34ba3aab291281ec8473f9dd23ef9b83>)에 오늘 작업 내용을 추가해줘.
> [오늘 한 것]: 1주차 데이터 수집 완료 — ranking/product/review 크롤러 3개 구현, 200개 상품 18,695건 리뷰 SQLite 저장
> [배운 점 / 의사결정]:
>   - 올리브영은 JS 렌더링 필수 → Playwright 선택
>   - 리뷰 API는 직접 호출 불가(CORS) → 페이지 response 인터셉트 방식으로 해결
>   - IP Rate Limit 발생 → 0건 감지 시 60초 대기 + 새 세션 재시도 로직 추가
>   - CSS Module 해시 suffix 문제 → class*= 패턴 매칭으로 해결
> [다음 작업]: 2주차 EDA (notebooks/01_eda.ipynb)"

## Notion 포트폴리오 링크

> 진행 상황·회고는 노션에 정리. 코드는 깃·여기. 두 개 동기화는 사용자가 수동으로.

- 메인 페이지: <https://www.notion.so/34ba3aab291281399ffcc616459608d9>
- About Me: <https://www.notion.so/34ba3aab29128138abc9cf42269a5c71>
- Skills & Tools: <https://www.notion.so/34ba3aab29128154b34df2c144db4b74>
- Learning Log: <https://www.notion.so/34ba3aab2912818681e5fcba32da70ff>
- 올영 프로젝트 상세: <https://www.notion.so/34ba3aab291281ec8473f9dd23ef9b83>

## 현재 상태 (2026-06-05)

- ✅ **1주차 데이터 수집 완료** (2026-04-28)
  - products 200 / rankings 200 / reviews 18,695
  - 크롤러 3종 (`ranking.py` / `product.py` / `review.py`) 구현 완료
  - Rate Limit 해결: 0건 감지 시 60초 대기 + 새 컨텍스트 재시도
  - 상세 스펙은 아래 표 참고
- ✅ **2주차 EDA 완료** — `notebooks/01_eda.ipynb`
  - 라벨링 정책 확정: `is_hit = (rank ≤ 30)`, 31~70 drop
- ✅ **3주차 피처 엔지니어링 완료** — `notebooks/02_features.ipynb`, `data/processed/features.parquet` (119 × 32)
  - 16피처 (핵심 9 + 보조 1 + 메타 5 + flag 2) → 4주차에서 다중공선성 정리로 19피처
  - 🎯 evangelist 가설 정립 (반직관 3개: photo↓ / length↓ / drift↓ → "초기 evangelist → 대중 확산으로 희석")
- ✅ **4주차 베이스라인 로지스틱 회귀 완료** — `notebooks/03_modeling.ipynb`
  - ROC-AUC **0.5417** / AP 0.5245 (의도적으로 약한 베이스라인)
  - evangelist 3개·discount·`sub_크림` TOP 5 신호 검증, 분산 가설은 *선형 모델 한계* 입증 (6주차 LightGBM 대비)
  - 에러 분석에서 가설 진화: **빠른 hit** (모델이 잡음) vs **느린 hit** (FN 4개, 모델이 놓침) 2단계 분리
- ✅ **5주차 BERTopic 텍스트 분석 완료** — `notebooks/04_text_analysis.ipynb` (2026-06-05)
  - 카테고리별 별도 fit (메이크업 24토픽 / 스킨케어, 통합 fit은 도메인 균질성으로 실패)
  - 4 가설 검증: Q1 부분 / Q2 반직관 발견 / **Q3 강하게 검증 (★ 5주차 최대 성과)** / Q4 검증
  - 🎯 **Q3 핵심**: fast_hit early 자발적 40.6% → late 29.8% (↓10.8%p), non-hit은 정반대 48.3%→60.4%
  - → evangelist 가설을 *텍스트로 독립 검증* (4주차 = 숫자 / 5주차 = 단어, 같은 결론)
  - 산출물: `features_v2.parquet` (119 × 37, 텍스트 피처 5개 추가), `reports/figures/` PNG 6장 (분석 3 + BERTopic native 3)
  - 신규 텍스트 피처: `evangelist_early_ratio`, `topic_shift`, `ad_ratio_2wk`, `voluntary_ratio_2wk`, `topic_diversity`
- ⏳ **다음**: 6주차 LightGBM + SHAP → `notebooks/05_modeling_lgbm.ipynb`
  - 비교 기준: 4주차 AUC 0.5417 → LightGBM이 분산 가설(std 1.94배)을 변별력으로 흡수하는지
  - 텍스트 피처 5개 추가 효과 측정 (`evangelist_early_ratio` 단독 기여 SHAP)

### DB 최종 현황 (2026-04-28)
| 테이블 | 행 수 | 비고 |
|---|---|---|
| products | 200개 | 스킨케어·색조 Top 100 × 2카테고리 |
| rankings | 200개 | 2026-04-27 스냅샷 |
| reviews | 18,695건 | 상품당 14~100건, 평균 93건 |

리뷰 날짜 범위: 2022-03-25 ~ 2026-04-28

### product.py 수집 스펙 (2026-04-27 분석)
| 필드 | selector |
|---|---|
| 상품명 | `h3[class*="GoodsDetailInfo_title"]` |
| 브랜드 | `button[class*="TopUtils_btn-brand"]` |
| 원가 | `s[class*="price-before"]` |
| 판매가 | `span[class*="GoodsDetailInfo_price__\w"]` |
| 평점 | `span.rating` → 숫자 추출 |
| 리뷰 수 | `div[class*="ReviewArea_review-count"]` → 숫자 추출 |
| 카테고리 | `div[class*="Breadcrumb_breadcrumb-inner"] a` 순서 |
| 출시일 | 상세 페이지에 없음 → NULL, review.py 최초 리뷰일로 채울 예정 |

### 베스트 페이지 크롤링 스펙 (분석 완료)

| 항목 | 내용 |
|---|---|
| URL | `POST https://www.oliveyoung.co.kr/store/main/getBestList.do` |
| 상품 컨테이너 | `<ul class="cate_prd_list">` × 25개 (4개씩 × 25줄 = 100개) |
| 상품 ID | `<a data-ref-goodsno="A000000XXXXXX">` |
| 순위 | `<span class="thumb_flag best">01</span>` 텍스트 |
| 스킨케어 필터 | `dispCatNo=900000100100001` + `fltDispCatNo=10000010001` |
| 색조 메이크업 필터 | `dispCatNo=900000100100001` + `fltDispCatNo=10000010002` |
| 페이지네이션 | 없음 (1페이지에 Top 100 전부) |

### review.py 수집 스펙 (2026-04-27 분석)
| 항목 | 내용 |
|---|---|
| 진입 URL | `getGoodsDetail.do?goodsNo=XXX&tab=review` |
| 로딩 방식 | 스크롤 무한 로딩 (10건/회) |
| 인터셉트 | `m.oliveyoung.co.kr/review/api/v2/reviews/cursor` response |
| 피부타입 | `profileDto.skinType` 코드값 (ex. "A02") — 2주차 EDA 때 디코딩 예정 |
| 출시일 추정 | `update_launch_dates()` 로 `MIN(written_at)` → `launch_date_est` 업데이트 |

## 다음 세션 추천 시작 멘트

> "@CLAUDE.md 읽고 메모리 확인해줘. 5주차 BERTopic 완료, AUC 0.54 베이스라인 위에 LightGBM으로 분산 가설 흡수 + 텍스트 피처 5개 추가 효과 측정. `notebooks/05_modeling_lgbm.ipynb` 골격부터 만들자."
