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


async def run_search(query: str, limit: int, since: str | None = None):
    logger.info("cli_search_mode_started", query=query, limit=limit, since=since)
    client = TwscrapeClient()
    ok = await client.initialize()
    if not ok:
        logger.error("scraper_initialization_failed", msg="Ensure accounts.txt exists and has credentials.")
        sys.exit(1)

    count = 0
    new_count = 0
    edge_count = 0

    try:
        async with get_async_session() as session:
            async for tweet in client.search(query=query, limit=limit, since=since):
                is_new, n_edges = await persist_tweet_pipeline(session, tweet)
                count += 1
                if is_new:
                    new_count += 1
                edge_count += n_edges
                print(f"[{count}/{limit}] Scraped tweet {tweet.post_id} from @{tweet.user.handle if tweet.user else 'unknown'} | New: {is_new} | Edges: {n_edges}")

        logger.info("cli_search_completed", total_scraped=count, new_saved=new_count, edges_saved=edge_count)
    except Exception as ex:
        logger.error("cli_search_error", error=str(ex))
        sys.exit(1)


async def run_poll(query: str, interval_minutes: int, limit_per_poll: int = 30):
    logger.info("cli_poll_mode_started", query=query, interval_minutes=interval_minutes)
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

    args = parser.parse_args()

    if args.mode == "search":
        asyncio.run(run_search(args.query, args.limit, args.since))
    elif args.mode == "poll":
        asyncio.run(run_poll(args.query, args.interval))


if __name__ == "__main__":
    main()
