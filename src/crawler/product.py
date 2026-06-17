"""2층 크롤러: 상품 상세 페이지에서 메타데이터 수집.

`rankings` 테이블에 있는 product_id를 받아 상세 페이지를 순회하며
`products` 테이블에 적재한다.

페이지 구조 (2026-04-27 분석):
    - URL: https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=XXXX
    - 상품명: h3[class*="GoodsDetailInfo_title"]
    - 브랜드: button[class*="TopUtils_btn-brand"]
    - 원가:   s[class*="price-before"]
    - 판매가:  span[class*="GoodsDetailInfo_price__"] (해시 suffix 있음)
    - 평점:   span.rating  → "평점4.9" 에서 숫자 추출
    - 리뷰 수: div[class*="ReviewArea_review-count"] → "리뷰34,065건" 에서 숫자 추출
    - 카테고리: div[class*="Breadcrumb_breadcrumb-inner"] 내 a 태그 순서
    - 출시일:  상세 페이지에 없음 → NULL, review.py에서 최초 리뷰일로 채울 예정
"""

import asyncio
import re
import sqlite3
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from tqdm import tqdm

PRODUCT_BASE_URL = (
    "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do"
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# 공개 인터페이스
# ---------------------------------------------------------------------------

def crawl_product_detail(product_id: str) -> dict:
    """단일 상품 상세 페이지 크롤링 (테스트·단건 수집용).

    Returns:
        products 테이블 한 행에 대응하는 dict
    """
    return asyncio.run(_fetch_products_batch([product_id]))[0]


def crawl_products_from_db(
    db_path: str | Path,
    delay_s: float = 1.5,
    overwrite: bool = False,
) -> list[dict]:
    """rankings 테이블의 상품 중 products에 없는 것을 일괄 크롤링.

    Args:
        db_path:   SQLite DB 경로
        delay_s:   상품 간 대기 시간 (초). 너무 빠르면 차단 위험.
        overwrite: True면 이미 수집된 상품도 재수집.
    """
    db_path = Path(db_path)
    product_ids = _get_uncrawled_ids(db_path, overwrite)
    if not product_ids:
        print("수집할 신규 상품 없음.")
        return []
    print(f"수집 대상: {len(product_ids)}개 상품")
    return asyncio.run(_fetch_products_batch(product_ids, delay_s))


# ---------------------------------------------------------------------------
# 내부 구현
# ---------------------------------------------------------------------------

def _get_uncrawled_ids(db_path: Path, overwrite: bool) -> list[str]:
    """rankings에 있고 products에 없는 product_id 목록 반환."""
    with sqlite3.connect(db_path) as conn:
        if overwrite:
            rows = conn.execute(
                "SELECT DISTINCT product_id FROM rankings"
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT DISTINCT r.product_id
                   FROM rankings r
                   LEFT JOIN products p USING (product_id)
                   WHERE p.product_id IS NULL"""
            ).fetchall()
    return [r[0] for r in rows]


async def _fetch_products_batch(
    product_ids: list[str], delay_s: float = 1.5
) -> list[dict]:
    """브라우저 하나로 여러 상품을 순차 수집한다."""
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=USER_AGENT)

        for i, product_id in enumerate(tqdm(product_ids, desc="상품 상세 수집")):
            url = f"{PRODUCT_BASE_URL}?goodsNo={product_id}"
            try:
                await page.goto(url, wait_until="networkidle")
                await page.wait_for_timeout(1500)
                html = await page.content()
                record = _parse_product_html(html, product_id, url)
                results.append(record)
            except Exception as exc:
                tqdm.write(f"  [경고] {product_id} 수집 실패: {exc}")
                results.append(
                    {"product_id": product_id, "name": None, "_error": str(exc)}
                )

            if i < len(product_ids) - 1:
                await asyncio.sleep(delay_s)

        await browser.close()
    return results


def _parse_product_html(html: str, product_id: str, url: str) -> dict:
    """렌더링된 HTML에서 상품 메타데이터를 추출한다."""
    soup = BeautifulSoup(html, "lxml")

    name = _text(soup.find("h3", class_=re.compile(r"GoodsDetailInfo_title")))
    brand = _text(soup.find("button", class_=re.compile(r"TopUtils_btn-brand")))

    price_original = _parse_price(
        _text(soup.find("s", class_=re.compile(r"price.before")))
    )
    # 판매가: GoodsDetailInfo_price__ + 해시 suffix (할인가 없으면 원가와 동일)
    price_el = soup.find("span", class_=re.compile(r"GoodsDetailInfo_price__\w"))
    price = _parse_price(_text(price_el))
    if price is None:
        price = price_original

    rating_avg = None
    rating_el = soup.find("span", class_="rating")
    if rating_el:
        m = re.search(r"[\d.]+", rating_el.get_text())
        if m:
            rating_avg = float(m.group())

    review_count_total = None
    review_el = soup.find(class_=re.compile(r"ReviewArea_review-count"))
    if review_el:
        m = re.search(r"[\d,]+", review_el.get_text())
        if m:
            review_count_total = int(m.group().replace(",", ""))

    category_main = category_sub = None
    bc = soup.find(class_=re.compile(r"Breadcrumb_breadcrumb-inner"))
    if bc:
        links = [a.get_text(strip=True) for a in bc.find_all("a")]
        if links:
            category_main = links[0]
        if len(links) >= 2:
            category_sub = links[1]

    return {
        "product_id": product_id,
        "name": name or "",
        "brand": brand,
        "category_main": category_main,
        "category_sub": category_sub,
        "price": price,
        "price_original": price_original,
        "launch_date_est": None,  # review.py에서 최초 리뷰일로 채움
        "review_count_total": review_count_total,
        "rating_avg": rating_avg,
        "url": url,
    }


def _text(el) -> str | None:
    return el.get_text(strip=True) if el else None


def _parse_price(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"[\d,]+", text)
    return int(m.group().replace(",", "")) if m else None


# ---------------------------------------------------------------------------
# DB 저장
# ---------------------------------------------------------------------------

def save_products(records: list[dict], db_path: str | Path) -> None:
    """products 테이블에 upsert.

    파싱 실패 레코드(_error 키 존재)는 건너뛴다.
    """
    valid = [r for r in records if "_error" not in r and r.get("name")]
    if not valid:
        print("  저장할 유효 데이터 없음.")
        return

    db_path = Path(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO products
               (product_id, name, brand, category_main, category_sub,
                price, price_original, launch_date_est,
                review_count_total, rating_avg, url)
               VALUES
               (:product_id, :name, :brand, :category_main, :category_sub,
                :price, :price_original, :launch_date_est,
                :review_count_total, :rating_avg, :url)""",
            valid,
        )
        conn.commit()

    skipped = len(records) - len(valid)
    print(f"  저장 완료: {len(valid)}개 → products" + (f" (실패 {skipped}개 제외)" if skipped else ""))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="올리브영 상품 상세 크롤러")
    parser.add_argument("--db", default="data/raw/oliveyoung.db", help="DB 파일 경로")
    parser.add_argument("--product-id", help="단건 테스트용 상품 ID")
    parser.add_argument("--delay", type=float, default=1.5, help="상품 간 대기(초)")
    parser.add_argument("--overwrite", action="store_true", help="기존 수집 상품도 재수집")
    parser.add_argument("--save", action="store_true", help="결과를 DB에 저장")
    args = parser.parse_args()

    if args.product_id:
        print(f"[product] 단건 수집: {args.product_id}")
        records = [crawl_product_detail(args.product_id)]
        for k, v in records[0].items():
            print(f"  {k}: {v}")
    else:
        records = crawl_products_from_db(args.db, args.delay, args.overwrite)
        print(f"[product] 수집 완료: {len(records)}개")
        for r in records[:3]:
            print(f"  {r['product_id']}  {r.get('brand','')}  {r.get('name','')[:40]}")

    if args.save and records:
        save_products(records, args.db)
