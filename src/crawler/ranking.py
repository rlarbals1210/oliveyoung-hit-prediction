"""1층 크롤러: 카테고리 랭킹 페이지에서 상품 ID 목록 수집.

올리브영 판매 베스트 페이지를 카테고리별로 순회하며 상품 ID와 순위를
`rankings` 테이블에 적재한다. 같은 상품이 카테고리·날짜별로 여러 행을 가진다.

수집 대상:
    - 스킨케어 Top 100
    - 색조 메이크업 Top 100

페이지 구조 (2026-04-26 분석):
    - URL: POST https://www.oliveyoung.co.kr/store/main/getBestList.do
    - 카테고리 필터: .common-menu 내 button[data-ref-dispcatno] 클릭
    - 상품 컨테이너: ul.cate_prd_list × 25개 (4개씩 = 100개, 페이지네이션 없음)
    - 상품 ID: a[data-ref-goodsno]
    - 순위: span.thumb_flag 텍스트
"""

import asyncio
import re
import sqlite3
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

BASE_URL = "https://www.oliveyoung.co.kr/store/main/getBestList.do"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# category 식별자 → fltDispCatNo (common-menu 버튼 data-ref-dispcatno 값)
CATEGORY_MAP: dict[str, str] = {
    "skincare": "10000010001",
    "makeup": "10000010002",
}

# DB 저장 시 사용하는 카테고리 레이블
CATEGORY_LABEL: dict[str, str] = {
    "skincare": "스킨케어",
    "makeup": "색조메이크업",
}


def crawl_category_ranking(category: str, top_n: int = 100) -> list[dict]:
    """카테고리 랭킹 페이지를 크롤링해 상품 ID·순위 목록을 반환.

    Args:
        category: 카테고리 식별자 ("skincare" | "makeup")
        top_n: 가져올 상위 상품 개수 (최대 100)

    Returns:
        [{"product_id": str, "rank": int, "category": str}, ...]
        rank 오름차순 정렬.
    """
    if category not in CATEGORY_MAP:
        raise ValueError(f"지원하지 않는 카테고리: {category!r}. 가능: {list(CATEGORY_MAP)}")
    return asyncio.run(_fetch_ranking_page(category, top_n))


async def _fetch_ranking_page(category: str, top_n: int) -> list[dict]:
    """Playwright로 카테고리 필터 버튼을 클릭 후 HTML을 수집한다."""
    flt_cat_no = CATEGORY_MAP[category]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=USER_AGENT)

        await page.goto(BASE_URL, wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # common-menu 내 카테고리 버튼 클릭 → form POST 자동 발생
        selector = f".common-menu button[data-ref-dispcatno='{flt_cat_no}']"
        await page.click(selector)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1500)

        html = await page.content()
        await browser.close()

    return _parse_ranking_html(html, category, top_n)


def _parse_ranking_html(html: str, category: str, top_n: int) -> list[dict]:
    """렌더링된 HTML에서 순위·상품 ID를 추출한다."""
    soup = BeautifulSoup(html, "lxml")
    results = []

    for ul in soup.find_all("ul", class_="cate_prd_list"):
        for li in ul.find_all("li", recursive=False):
            span = li.find("span", class_=re.compile(r"thumb_flag"))
            a = li.find("a", attrs={"data-ref-goodsno": True})
            if not (span and a):
                continue

            rank_text = span.get_text(strip=True)
            if not rank_text.isdigit():
                continue

            rank = int(rank_text)
            if rank > top_n:
                continue

            results.append(
                {
                    "product_id": a["data-ref-goodsno"],
                    "rank": rank,
                    "category": CATEGORY_LABEL[category],
                }
            )

    return sorted(results, key=lambda x: x["rank"])


def save_rankings(records: list[dict], db_path: str | Path) -> None:
    """rankings 테이블에 오늘 날짜 스냅샷으로 적재.

    같은 날짜·카테고리 조합이 이미 있으면 덮어쓴다 (재실행 안전).
    """
    if not records:
        print("  저장할 데이터 없음.")
        return

    db_path = Path(db_path)
    today = date.today().isoformat()
    category = records[0]["category"]

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "DELETE FROM rankings WHERE snapshot_date = ? AND category = ?",
            (today, category),
        )
        conn.executemany(
            """INSERT INTO rankings (product_id, category, rank, snapshot_date)
               VALUES (:product_id, :category, :rank, :snapshot_date)""",
            [{"snapshot_date": today, **r} for r in records],
        )
        conn.commit()

    print(f"  저장 완료: {len(records)}개 → rankings (date={today}, category={category})")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="올리브영 카테고리 랭킹 크롤러")
    parser.add_argument(
        "--category",
        choices=list(CATEGORY_MAP),
        default="skincare",
        help="크롤링 카테고리 (기본: skincare)",
    )
    parser.add_argument("--top-n", type=int, default=100, help="상위 N개 수집 (기본: 100)")
    parser.add_argument("--db", default="data/raw/oliveyoung.db", help="DB 파일 경로")
    parser.add_argument("--save", action="store_true", help="결과를 DB에 저장")
    args = parser.parse_args()

    print(f"[ranking] 크롤링 시작: {args.category} Top {args.top_n}")
    records = crawl_category_ranking(args.category, args.top_n)

    print(f"[ranking] 수집 완료: {len(records)}개")
    for r in records[:5]:
        print(f"  {r['rank']:>3}위  {r['product_id']}  ({r['category']})")
    if len(records) > 5:
        print(f"  ... 외 {len(records) - 5}개")

    if args.save:
        save_rankings(records, args.db)
