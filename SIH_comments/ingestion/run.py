"""
CLI entrypoint for ingestion.

Usage:
  python -m ingestion.run --mode search --query "AI" --since 2026-08-01 --limit 50
  python -m ingestion.run --mode poll --query "AI" --interval 15
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime

from config import get_settings
from db.session import get_async_session
from ingestion.client import TwscrapeClient
from ingestion.store import persist_tweet_pipeline
from logging_config import get_logger, setup_logging

setup_logging()
logger = get_logger("ingestion.cli")


async def run_search(
    query: str,
    limit: int,
    since: str | None = None,
    scrape_comments: bool = True,
    comments_limit: int = 10,
):
    logger.info(
        "cli_search_mode_started",
        query=query,
        limit=limit,
        since=since,
        scrape_comments=scrape_comments,
        comments_limit=comments_limit,
    )
    client = TwscrapeClient()
    ok = await client.initialize()
    if not ok:
        logger.error("scraper_initialization_failed", msg="Ensure accounts.txt exists and has credentials.")
        sys.exit(1)

    count = 0
    new_count = 0
    edge_count = 0
    total_comments_scraped = 0

    try:
        async with get_async_session() as session:
            async for tweet in client.search(query=query, limit=limit, since=since):
                is_new, n_edges = await persist_tweet_pipeline(session, tweet)
                count += 1
                if is_new:
                    new_count += 1
                edge_count += n_edges
                print(f"[{count}/{limit}] Scraped tweet {tweet.post_id} from @{tweet.user.handle if tweet.user else 'unknown'} | New: {is_new} | Edges: {n_edges}")

                # Scrape comments / replies for this post
                if scrape_comments and (tweet.reply_count > 0 or tweet.reply_count is None):
                    c_count = 0
                    try:
                        async for comment in client.get_replies(tweet.post_id, limit=comments_limit):
                            if not comment.in_reply_to_post_id:
                                comment.in_reply_to_post_id = tweet.post_id
                            if not comment.in_reply_to_user_id and tweet.user:
                                comment.in_reply_to_user_id = tweet.user.user_id
                            c_new, c_edges = await persist_tweet_pipeline(session, comment)
                            c_count += 1
                            total_comments_scraped += 1
                            edge_count += c_edges
                            if c_new:
                                new_count += 1
                            c_user = comment.user.handle if comment.user else "unknown"
                            print(f"    └── [Comment {c_count}] @{c_user}: {comment.text[:50]}... | New: {c_new} | Edges: {c_edges}")
                    except Exception as c_err:
                        logger.warning("comment_scrape_skipped", post_id=tweet.post_id, error=str(c_err))

        logger.info(
            "cli_search_completed",
            total_scraped=count,
            comments_scraped=total_comments_scraped,
            new_saved=new_count,
            edges_saved=edge_count,
        )
    except Exception as ex:
        logger.error("cli_search_error", error=str(ex))
        sys.exit(1)


async def run_poll(
    query: str,
    interval_minutes: int,
    limit_per_poll: int = 30,
    scrape_comments: bool = True,
    comments_limit: int = 10,
):
    logger.info(
        "cli_poll_mode_started",
        query=query,
        interval_minutes=interval_minutes,
        scrape_comments=scrape_comments,
    )
    client = TwscrapeClient()
    ok = await client.initialize()
    if not ok:
        logger.error("scraper_initialization_failed", msg="Ensure accounts.txt exists and has credentials.")
        sys.exit(1)

    seen_ids = set()

    while True:
        poll_time = datetime.now().isoformat()
        print(f"\n--- [Polling Tick at {poll_time}] Query: {query} ---")
        try:
            async with get_async_session() as session:
                new_in_poll = 0
                async for tweet in client.search(query=query, limit=limit_per_poll):
                    if tweet.post_id in seen_ids:
                        continue
                    seen_ids.add(tweet.post_id)
                    is_new, _ = await persist_tweet_pipeline(session, tweet)
                    if is_new:
                        new_in_poll += 1
                        print(f"  + New post: {tweet.post_id} | @{tweet.user.handle if tweet.user else 'unknown'}: {tweet.text[:60]}...")

                    if scrape_comments and (tweet.reply_count > 0 or tweet.reply_count is None):
                        c_count = 0
                        try:
                            async for comment in client.get_replies(tweet.post_id, limit=comments_limit):
                                if not comment.in_reply_to_post_id:
                                    comment.in_reply_to_post_id = tweet.post_id
                                if not comment.in_reply_to_user_id and tweet.user:
                                    comment.in_reply_to_user_id = tweet.user.user_id
                                c_new, _ = await persist_tweet_pipeline(session, comment)
                                c_count += 1
                                if c_new:
                                    new_in_poll += 1
                                    c_user = comment.user.handle if comment.user else "unknown"
                                    print(f"      └── [Comment {c_count}] @{c_user}: {comment.text[:50]}...")
                        except Exception as c_err:
                            logger.warning("poll_comment_scrape_skipped", post_id=tweet.post_id, error=str(c_err))

                print(f"Poll completed. New posts ingested: {new_in_poll}")
        except Exception as ex:
            logger.error("cli_poll_tick_error", error=str(ex))

        print(f"Sleeping for {interval_minutes} minutes before next poll...")
        await asyncio.sleep(interval_minutes * 60)


def main():
    parser = argparse.ArgumentParser(description="Audience Intelligence Live Ingestion CLI")
    parser.add_argument("--mode", choices=["search", "poll"], default="search", help="Collection mode")
    parser.add_argument("--query", type=str, required=True, help="Search query or hashtag (e.g. 'AI' or '#fintech')")
    parser.add_argument("--since", type=str, default=None, help="Since date (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, default=50, help="Max tweets to fetch in search mode")
    parser.add_argument("--interval", type=int, default=15, help="Minutes between polling loops")
    parser.add_argument("--scrape-comments", action="store_true", default=True, help="Scrape replies/comments for each post (default: True)")
    parser.add_argument("--no-scrape-comments", dest="scrape_comments", action="store_false", help="Disable comment scraping")
    parser.add_argument("--comments-limit", type=int, default=10, help="Max comments to fetch per post (default: 10)")

    args = parser.parse_args()

    if args.mode == "search":
        asyncio.run(run_search(args.query, args.limit, args.since, args.scrape_comments, args.comments_limit))
    elif args.mode == "poll":
        asyncio.run(run_poll(args.query, args.interval, scrape_comments=args.scrape_comments, comments_limit=args.comments_limit))


if __name__ == "__main__":
    main()
