"""SQLite 스키마 정의 및 초기화.

3개 raw 테이블 (products, rankings, reviews) 을 생성하고 인덱스를 건다.
파생 테이블 (product_features) 은 분석 단계에서 별도로 만든다.

사용:
    python -m src.db.schema --db data/raw/oliveyoung.db
"""

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
-- 상품 마스터 (1상품 = 1행)
CREATE TABLE IF NOT EXISTS products (
    product_id          TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    brand               TEXT,
    category_main       TEXT,
    category_sub        TEXT,
    price               INTEGER,
    price_original      INTEGER,
    launch_date_est     DATE,
    review_count_total  INTEGER,
    rating_avg          REAL,
    url                 TEXT,
    crawled_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 랭킹 스냅샷 (날짜·카테고리별로 같은 상품이 여러 행)
CREATE TABLE IF NOT EXISTS rankings (
    snapshot_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      TEXT NOT NULL,
    category        TEXT NOT NULL,
    rank            INTEGER NOT NULL,
    snapshot_date   DATE NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);
CREATE INDEX IF NOT EXISTS idx_rankings_product_date
    ON rankings(product_id, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_rankings_category_date_rank
    ON rankings(category, snapshot_date, rank);

-- 리뷰 원본 (가장 큰 테이블)
CREATE TABLE IF NOT EXISTS reviews (
    review_id           TEXT PRIMARY KEY,
    product_id          TEXT NOT NULL,
    rating              INTEGER,
    content             TEXT,
    written_at          DATE,
    helpful_count       INTEGER,
    has_photo           INTEGER,  -- 0/1
    author_id_masked    TEXT,
    author_skin_type    TEXT,     -- nullable
    crawled_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);
CREATE INDEX IF NOT EXISTS idx_reviews_product
    ON reviews(product_id);
CREATE INDEX IF NOT EXISTS idx_reviews_written_at
    ON reviews(written_at);
"""


def init_database(db_path: str | Path) -> None:
    """주어진 경로에 SQLite DB를 초기화하고 스키마를 적용한다."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    print(f"DB initialized: {db_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SQLite DB 초기화")
    parser.add_argument(
        "--db",
        default="data/raw/oliveyoung.db",
        help="DB 파일 경로 (기본: data/raw/oliveyoung.db)",
    )
    args = parser.parse_args()
    init_database(args.db)
