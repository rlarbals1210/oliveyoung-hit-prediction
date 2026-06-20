"""raw 3테이블(SQLite)에서 모델 입력용 구조 피처 테이블을 빌드.

`notebooks/02_features.ipynb`(3주차)에서 검증된 피처 계산 로직을
재사용 가능한 함수로 정리한 모듈. 노트북과 동일한 `features.parquet`(119 × 32)를 생성한다.

빌드되는 피처 (구조 피처 — 텍스트/BERTopic 피처는 5주차 04_text_analysis 별도):
    윈도우(출시 후 14일) 집계:
    - reviews_2wk_count          : 첫 14일 리뷰 수
    - reviews_2wk_velocity_slope : 일별 리뷰 수의 1차 회귀 기울기
    - rating_2wk_mean / _std     : 첫 14일 평균/표준편차 별점
    - photo_review_ratio_2wk     : 포토 리뷰 비율
    - review_length_mean_2wk     : 평균 리뷰 글자 수
    - rating_drift               : 후반(7~13일) 평점 mean − 전반(0~6일) 평점 mean
                                   (※ '현재 평점 대비'가 아니라 14일 윈도우 *내부* 전후 비교 — 미래 정보 누수 없음)
    - review_burst_3d            : 14일 안 슬라이딩 3일 윈도우 최대 리뷰 합
    - skin_type_diversity        : 작성자 피부타입 Shannon entropy(bits)
    - skin_type_n_unique         : 등장한 고유 피부타입 수
    메타:
    - is_makeup, category_sub_group(+더미 5개), brand_freq, log_price, discount_rate
    플래그:
    - has_drift_signal, has_std_signal (NaN 여부 자체를 피처화)
    레이블:
    - is_hit  (현재 카테고리 rank <= 30 = 1, rank >= 71 = 0; 31~70위는 제외)

라벨링 설계상 rank 31~70위 상품은 학습 셋에서 제외(양 끝단 대비). 14일 윈도우 내
리뷰가 0건인 상품 1개는 drop -> 최종 119행.
"""

from __future__ import annotations

import argparse

import duckdb
import numpy as np
import pandas as pd

WINDOW_DAYS = 14
DRIFT_SPLIT_DAY = 7  # 전반 [0, 7), 후반 [7, 14)

# 스킨케어 sub 카테고리 n<10 5개는 '기타스킨케어'로 통합 (3주차 결정)
CATEGORY_SUB_GROUP_MAP = {
    "베이스메이크업": "베이스메이크업",
    "아이메이크업": "아이메이크업",
    "립메이크업": "립메이크업",
    "크림": "크림",
    "에센스/세럼/앰플": "에센스/세럼/앰플",
    "로션": "기타스킨케어",
    "미스트/오일": "기타스킨케어",
    "스킨/토너": "기타스킨케어",
    "스킨케어 디바이스": "기타스킨케어",
    "스킨케어세트": "기타스킨케어",
}

FINAL_COLUMNS = [
    "product_id", "is_hit", "category", "launch_date_est", "cutoff_date",
    "reviews_2wk_count", "reviews_2wk_velocity_slope", "rating_2wk_mean",
    "rating_2wk_std", "photo_review_ratio_2wk", "review_length_mean_2wk",
    "rating_drift", "review_burst_3d", "skin_type_diversity", "skin_type_n_unique",
    "category_main", "category_sub", "brand", "price", "price_original",
    "is_makeup", "category_sub_group", "sub_립메이크업", "sub_베이스메이크업",
    "sub_아이메이크업", "sub_에센스/세럼/앰플", "sub_크림", "brand_freq",
    "log_price", "discount_rate", "has_drift_signal", "has_std_signal",
]


def _velocity_slope(group: pd.DataFrame) -> float:
    """14일 일별 리뷰수의 1차 회귀 기울기 (zero-fill 후 polyfit)."""
    daily = group["days_since_launch"].value_counts().reindex(range(WINDOW_DAYS), fill_value=0)
    return np.polyfit(np.arange(WINDOW_DAYS), daily.values, 1)[0]


def _rating_drift(group: pd.DataFrame) -> float:
    """후반(7~13일) 평점 mean − 전반(0~6일) 평점 mean. 한쪽 0건이면 NaN."""
    first = group.loc[group["days_since_launch"] < DRIFT_SPLIT_DAY, "rating"]
    second = group.loc[group["days_since_launch"] >= DRIFT_SPLIT_DAY, "rating"]
    if len(first) == 0 or len(second) == 0:
        return np.nan
    return second.mean() - first.mean()


def _burst_3d(group: pd.DataFrame) -> float:
    """14일 안 슬라이딩 3일 윈도우의 최대 리뷰 합."""
    daily = group["days_since_launch"].value_counts().reindex(range(WINDOW_DAYS), fill_value=0)
    return daily.rolling(3).sum().max()


def _skin_type_diversity(group: pd.DataFrame) -> float:
    """작성자 피부타입 Shannon entropy(bits). NULL은 'unknown'으로 보존."""
    counts = group["author_skin_type"].fillna("unknown").value_counts()
    p = counts / counts.sum()
    return float(-np.sum(p * np.log2(p)))


def _load_raw(con):
    """duckdb 연결(oy 스키마 ATTACH됨)에서 label_df, base_df, meta_df를 읽어 반환."""
    label_df = con.sql(
        """
        SELECT p.product_id,
               CASE WHEN r.rank <= 30 THEN 1 ELSE 0 END AS is_hit,
               r.category,
               p.launch_date_est,
               p.launch_date_est + 14 AS cutoff_date
        FROM oy.products p
        JOIN oy.rankings r USING (product_id)
        WHERE r.rank <= 30 OR r.rank >= 71
        """
    ).df()
    con.register("label_df", label_df)
    base_df = con.execute(
        """
        SELECT r.product_id, r.written_at, r.rating, r.has_photo, r.content,
               r.author_skin_type,
               DATE_DIFF('day', p.launch_date_est, r.written_at) AS days_since_launch,
               LENGTH(r.content) AS review_length
        FROM oy.reviews r
        JOIN oy.products p ON r.product_id = p.product_id
        JOIN label_df l ON r.product_id = l.product_id
        WHERE r.written_at >= p.launch_date_est
          AND r.written_at < p.launch_date_est + INTERVAL '14 days'
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY r.product_id, r.written_at, r.content, r.author_skin_type
            ORDER BY r.review_id
        ) = 1
        """
    ).df()
    meta_df = con.execute(
        "SELECT product_id, category_main, category_sub, brand, price, price_original FROM oy.products"
    ).df()
    return label_df, base_df, meta_df


def assemble_features(label_df, base_df, meta_df):
    """라벨/윈도우베이스/메타 DataFrame에서 최종 피처 테이블(119 x 32)을 조립.

    데이터 로딩(SQL)과 분리되어 단위 테스트하기 쉽다.
    """
    g = base_df.groupby("product_id")
    features = label_df.copy()
    features = features.merge(g.size().rename("reviews_2wk_count"), on="product_id", how="left")
    features["reviews_2wk_count"] = features["reviews_2wk_count"].fillna(0).astype(int)
    features = features.merge(
        g.apply(_velocity_slope).rename("reviews_2wk_velocity_slope"), on="product_id", how="left"
    )
    agg_simple = g.agg(
        rating_2wk_mean=("rating", "mean"),
        rating_2wk_std=("rating", "std"),
        photo_review_ratio_2wk=("has_photo", "mean"),
        review_length_mean_2wk=("review_length", "mean"),
    ).reset_index()
    features = features.merge(agg_simple, on="product_id", how="left")
    features = features.merge(g.apply(_rating_drift).rename("rating_drift"), on="product_id", how="left")
    features = features.merge(g.apply(_burst_3d).rename("review_burst_3d"), on="product_id", how="left")
    features = features.merge(
        g.apply(_skin_type_diversity).rename("skin_type_diversity"), on="product_id", how="left"
    )
    features = features.merge(
        g["author_skin_type"].apply(lambda s: s.fillna("unknown").nunique()).rename("skin_type_n_unique"),
        on="product_id", how="left",
    )

    features = features.merge(meta_df, on="product_id", how="left")
    features["is_makeup"] = (features["category_main"] == "메이크업").astype(int)
    features["category_sub_group"] = features["category_sub"].map(CATEGORY_SUB_GROUP_MAP)
    dummies = pd.get_dummies(features["category_sub_group"], prefix="sub", drop_first=True).astype(int)
    features = pd.concat([features, dummies], axis=1)
    features["brand_freq"] = features["brand"].map(features["brand"].value_counts())
    features["log_price"] = np.log1p(features["price"])
    features["discount_rate"] = np.where(
        features["price_original"].notna() & (features["price_original"] > 0),
        (features["price_original"] - features["price"]) / features["price_original"] * 100,
        0.0,
    )

    features = features[features["reviews_2wk_count"] > 0].reset_index(drop=True)
    features["has_drift_signal"] = features["rating_drift"].notna().astype(int)
    features["has_std_signal"] = features["rating_2wk_std"].notna().astype(int)
    for col in ("rating_drift", "rating_2wk_std"):
        features[col] = features[col].fillna(0)
    return features[FINAL_COLUMNS]


def build_features(db_path: str = "data/raw/oliveyoung.db") -> pd.DataFrame:
    """raw 테이블에서 구조 피처 DataFrame을 만들어 반환 (119 x 32)."""
    con = duckdb.connect()
    con.execute(f"ATTACH '{db_path}' AS oy (TYPE sqlite)")
    label_df, base_df, meta_df = _load_raw(con)
    out = assemble_features(label_df, base_df, meta_df)
    con.close()
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="구조 피처 테이블 빌드")
    parser.add_argument("--db", default="data/raw/oliveyoung.db", help="SQLite raw DB 경로")
    parser.add_argument("--out", default="data/processed/features.parquet", help="출력 parquet 경로")
    args = parser.parse_args()

    df = build_features(args.db)
    df.to_parquet(args.out, index=False)
    df.to_csv(args.out.replace(".parquet", ".csv"), index=False, encoding="utf-8-sig")
    print(f"OK {df.shape} -> {args.out}")


if __name__ == "__main__":
    main()
