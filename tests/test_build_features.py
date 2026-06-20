"""build_features 모듈이 3주차 features.parquet를 재현하는지 검증.

실행: `uv run pytest tests/test_build_features.py`
(duckdb sqlite_scanner 확장이 필요 — 로컬 환경에서 동작)
"""
from pathlib import Path

import pandas as pd
import pytest

from src.features.build_features import build_features

DB = "data/raw/oliveyoung.db"
REF = "data/processed/features.parquet"


@pytest.mark.skipif(not Path(DB).exists() or not Path(REF).exists(),
                    reason="raw DB 또는 기준 parquet 없음")
def test_reproduces_features_parquet():
    got = build_features(DB).sort_values("product_id").reset_index(drop=True)
    ref = pd.read_parquet(REF).sort_values("product_id").reset_index(drop=True)

    assert got.shape == ref.shape == (119, 32)
    assert list(got.columns) == list(ref.columns)
    pd.testing.assert_frame_equal(got, ref, check_dtype=False, rtol=1e-6, atol=1e-6)
