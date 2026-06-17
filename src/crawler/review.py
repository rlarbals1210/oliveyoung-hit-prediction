"""3층 크롤러: 리뷰 페이지에서 리뷰 본문·메타 수집.

올리브영 상품 상세의 리뷰 탭을 스크롤해 무한 로딩을 트리거한다.
API 응답(reviews/cursor)을 response 인터셉트로 수집하므로 HTML 파싱 불필요.

접근 URL:
    https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=XXXX&tab=review

페이지 로딩 방식 (2026-04-27 분석):
    - 진입 시 첫 10건 자동 로드
    - 스크롤 아래로 → 10건씩 추가 로드 (무한 스크롤)
    - 인터셉트 URL: https://m.oliveyoung.co.kr/review/api/v2/reviews/cursor

리뷰 필드 매핑 (API JSON → DB):
    reviewId              → review_id
    goodsDto.goodsNumber  → product_id
    reviewScore           → rating
    content               → content
    createdDateTime       → written_at ("2026.03.15" → "2026-03-15")
    recommendCount        → helpful_count
    hasPhoto              → has_photo (bool → 0/1)
    profileDto.profileKey (MD5 앞 16자) → author_id_masked
    profileDto.skinType   → author_skin_type (nullable, 코드값 ex. "A02")
"""

import asyncio
import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright
from tqdm import tqdm

REVIEW_URL_TEMPLATE = (
    "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do"
    "?goodsNo={product_id}&tab=review"
)
REVIEW_API_PATTERN = "reviews/cursor"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
REVIEWS_PER_SCROLL = 10   # 스크롤 1회당 로드 건수 (고정)


# ---------------------------------------------------------------------------
# 공개 인터페이스
# ---------------------------------------------------------------------------

def crawl_product_reviews(product_id: str, max_reviews: int = 200) -> list[dict]:
    """단일 상품 리뷰 크롤링 (테스트·단건용)."""
    return asyncio.run(_fetch_reviews_batch([product_id], max_reviews))


def crawl_reviews_from_db(
    db_path: str | Path,
    max_reviews: int = 200,
    delay_s: float = 2.0,
    overwrite: bool = False,
) -> list[dict]:
    """products 테이블의 상품 중 reviews가 없는 것을 일괄 크롤링.

    Args:
        db_path:     SQLite DB 경로
        max_reviews: 상품당 최대 수집 리뷰 수
        delay_s:     상품 간 대기 시간 (초)
        overwrite:   True면 이미 리뷰가 있는 상품도 재수집
    """
    db_path = Path(db_path)
    product_ids = _get_uncrawled_ids(db_path, overwrite)
    if not product_ids:
        print("수집할 신규 상품 없음.")
        return []
    print(f"수집 대상: {len(product_ids)}개 상품 (상품당 최대 {max_reviews}건)")
    return asyncio.run(_fetch_reviews_batch(product_ids, max_reviews, delay_s))


# ---------------------------------------------------------------------------
# 내부 구현
# ---------------------------------------------------------------------------

def _get_uncrawled_ids(db_path: Path, overwrite: bool) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        if overwrite:
            rows = conn.execute(
                "SELECT DISTINCT product_id FROM products"
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT DISTINCT p.product_id
                   FROM products p
                   LEFT JOIN reviews r USING (product_id)
                   WHERE r.product_id IS NULL"""
            ).fetchall()
    return [r[0] for r in rows]


RATE_LIMIT_RETRY_WAIT = 60   # 0건 수집 시 재시도 전 대기(초) — IP 기반 Rate Limit 회복
CONTEXT_ROTATE_EVERY = 3    # N개 상품마다 브라우저 컨텍스트 교체


async def _fetch_reviews_batch(
    product_ids: list[str],
    max_reviews: int = 200,
    delay_s: float = 2.0,
) -> list[dict]:
    """브라우저 하나로 여러 상품 리뷰를 순차 수집한다.

    0건이 반환되면 IP Rate Limit으로 판단하고 RATE_LIMIT_RETRY_WAIT초 대기 후
    새 컨텍스트로 1회 재시도한다.
    """
    all_reviews = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=USER_AGENT)
        page = await ctx.new_page()
        context_usage = 0

        for i, product_id in enumerate(tqdm(product_ids, desc="리뷰 수집")):
            if context_usage >= CONTEXT_ROTATE_EVERY:
                await ctx.close()
                ctx = await browser.new_context(user_agent=USER_AGENT)
                page = await ctx.new_page()
                context_usage = 0

            try:
                reviews = await _fetch_one_product(page, product_id, max_reviews)

                # 0건 → Rate Limit 의심: 60초 대기 후 새 컨텍스트로 1회 재시도
                if len(reviews) == 0:
                    tqdm.write(f"  {product_id}: 0건 (Rate Limit 의심, {RATE_LIMIT_RETRY_WAIT}초 대기 후 재시도)")
                    await asyncio.sleep(RATE_LIMIT_RETRY_WAIT)
                    await ctx.close()
                    ctx = await browser.new_context(user_agent=USER_AGENT)
                    page = await ctx.new_page()
                    context_usage = 0
                    reviews = await _fetch_one_product(page, product_id, max_reviews)

                all_reviews.extend(reviews)
                tqdm.write(f"  {product_id}: {len(reviews)}건")
            except Exception as exc:
                tqdm.write(f"  [경고] {product_id} 실패: {exc}")

            context_usage += 1
            if i < len(product_ids) - 1:
                await asyncio.sleep(delay_s)

        await browser.close()

    return all_reviews


async def _fetch_one_product(page, product_id: str, max_reviews: int) -> list[dict]:
    """단일 상품 리뷰 탭을 스크롤하며 리뷰를 수집한다."""
    import json

    collected: list[dict] = []
    is_done = False

    async def on_response(resp):
        nonlocal is_done
        if REVIEW_API_PATTERN not in resp.url or is_done:
            return
        try:
            body = await resp.text()
            if not body:
                return
            data = json.loads(body).get("data") or {}
            items = data.get("goodsReviewList") or []
            for item in items:
                if len(collected) >= max_reviews:
                    is_done = True
                    break
                collected.append(_parse_review(item, product_id))
            if not data.get("hasNext"):
                is_done = True
        except Exception:
            pass

    page.on("response", on_response)
    try:
        url = REVIEW_URL_TEMPLATE.format(product_id=product_id)
        await page.goto(url, wait_until="load", timeout=40000)
        await page.wait_for_timeout(3000)

        # URL 파라미터로 탭이 활성화되지 않는 경우 리뷰 탭 버튼을 직접 클릭
        if len(collected) == 0:
            try:
                tab_btn = page.locator("[class*='GoodsDetailTabs_review']").first
                if await tab_btn.count() > 0:
                    await tab_btn.click()
                    await page.wait_for_timeout(2500)
            except Exception:
                pass

        # 필요한 만큼 스크롤
        max_scrolls = (max_reviews // REVIEWS_PER_SCROLL) + 2
        for _ in range(max_scrolls):
            if is_done or len(collected) >= max_reviews:
                break
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1200)
    finally:
        page.remove_listener("response", on_response)

    return collected[:max_reviews]


def _parse_review(item: dict, product_id: str) -> dict:
    profile = item.get("profileDto") or {}
    profile_key = profile.get("profileKey") or profile.get("memberNickname") or ""
    author_id_masked = hashlib.md5(profile_key.encode()).hexdigest()[:16]

    return {
        "review_id": str(item["reviewId"]),
        "product_id": product_id,
        "rating": item.get("reviewScore"),
        "content": item.get("content", ""),
        "written_at": _parse_date(item.get("createdDateTime", "")),
        "helpful_count": item.get("recommendCount", 0),
        "has_photo": 1 if item.get("hasPhoto") else 0,
        "author_id_masked": author_id_masked,
        "author_skin_type": profile.get("skinType"),
    }


def _parse_date(raw: str) -> str | None:
    """'2026.03.15' → '2026-03-15' (ISO 형식)."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y.%m.%d").strftime("%Y-%m-%d")
    except ValueError:
        return raw


# ---------------------------------------------------------------------------
# DB 저장
# ---------------------------------------------------------------------------

def save_reviews(records: list[dict], db_path: str | Path) -> None:
    """reviews 테이블에 upsert (같은 review_id는 덮어씀)."""
    if not records:
        print("  저장할 데이터 없음.")
        return

    db_path = Path(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO reviews
               (review_id, product_id, rating, content, written_at,
                helpful_count, has_photo, author_id_masked, author_skin_type)
               VALUES
               (:review_id, :product_id, :rating, :content, :written_at,
                :helpful_count, :has_photo, :author_id_masked, :author_skin_type)""",
            records,
        )
        conn.commit()
    print(f"  저장 완료: {len(records)}건 → reviews")


def update_launch_dates(db_path: str | Path) -> None:
    """최초 리뷰 작성일을 products.launch_date_est에 반영.

    리뷰 수집 후 한 번 실행한다. launch_date_est가 NULL인 상품만 업데이트.
    """
    db_path = Path(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """UPDATE products
               SET launch_date_est = (
                   SELECT MIN(written_at)
                   FROM reviews
                   WHERE reviews.product_id = products.product_id
               )
               WHERE launch_date_est IS NULL"""
        )
        conn.commit()
    print("  launch_date_est 업데이트 완료")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="올리브영 리뷰 크롤러")
    parser.add_argument("--db", default="data/raw/oliveyoung.db", help="DB 파일 경로")
    parser.add_argument("--product-id", help="단건 테스트용 상품 ID")
    parser.add_argument("--max-reviews", type=int, default=200, help="상품당 최대 리뷰 수")
    parser.add_argument("--delay", type=float, default=2.0, help="상품 간 대기(초)")
    parser.add_argument("--overwrite", action="store_true", help="기존 수집 상품도 재수집")
    parser.add_argument("--save", action="store_true", help="결과를 DB에 저장")
    parser.add_argument(
        "--update-launch-dates", action="store_true",
        help="수집 후 products.launch_date_est 업데이트"
    )
    args = parser.parse_args()

    if args.product_id:
        print(f"[review] 단건 수집: {args.product_id}")
        records = crawl_product_reviews(args.product_id, args.max_reviews)
        print(f"수집 완료: {len(records)}건")
        for r in records[:3]:
            print(f"  {r['review_id']}  {r['written_at']}  별점:{r['rating']}  {r['content'][:40]}")
    else:
        records = crawl_reviews_from_db(
            args.db, args.max_reviews, args.delay, args.overwrite
        )
        print(f"[review] 총 수집: {len(records)}건")

    if args.save and records:
        save_reviews(records, args.db)
        if args.update_launch_dates:
            update_launch_dates(args.db)
