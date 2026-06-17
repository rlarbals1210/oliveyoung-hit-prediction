"""raw 테이블에서 모델 입력용 product_features 테이블을 빌드.

3주차 이후, notebooks/02_features.ipynb 에서 검증된 피처 계산 로직을
이 파일로 옮겨 재사용 가능한 함수로 정리한다.

빌드할 피처 (계획):
    - reviews_2wk_count          : 출시 후 첫 2주 리뷰 수
    - reviews_2wk_velocity_slope : 일별 리뷰 수 증가율 (회귀 기울기)
    - rating_2wk_mean            : 첫 2주 평균 별점
    - rating_2wk_std             : 첫 2주 별점 분산
    - rating_drift               : 첫 2주 평점 - 현재 평점 (마케팅 거품 탐지)
    - photo_review_ratio_2wk     : 포토 리뷰 비율
    - review_length_mean_2wk     : 평균 리뷰 길이
    - topic_dominant             : BERTopic 주요 토픽 (5주차)
    - sentiment_score_mean       : 평균 감성 점수 (5주차)
    - is_hit                     : 레이블 (현재 카테고리 Top 50 안이면 1)
"""

import duckdb
import pandas as pd


def build_features(db_path: str = "data/raw/oliveyoung.db") -> pd.DataFrame:
    """raw 테이블에서 product_features DataFrame을 만들어 반환.

    Args:
        db_path: SQLite raw DB 경로

    Returns:
        product_id를 인덱스로 가지는 피처 DataFrame
    """
    raise NotImplementedError("3주차에 구현 예정 — 우선 notebooks/02_features.ipynb 에서 실험")


if __name__ == "__main__":
    df = build_features()
    print(df.head())
