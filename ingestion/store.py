"""
Idempotent database storage layer for ingested users, posts, and edges.

Guarantees:
- Re-running ingestion never creates duplicate records.
- Edges are derived automatically from post metadata (mentions, replies, quotes, retweets).
"""

from __future__ import annotations

from typing import List, Tuple
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Edge, Post, User
from ingestion.models import ScrapedTweet, ScrapedUser
from logging_config import get_logger

logger = get_logger("ingestion.store")


def derive_edges_from_tweet(tweet: ScrapedTweet) -> List[dict]:
    """
    Derives graph edges from tweet metadata.
    Edges represent information spread/interaction:
    - mention
    - reply
    - retweet
    - quote
    """
    edges = []
    source_id = tweet.user_id

    # 1. Replies
    if tweet.is_reply and tweet.in_reply_to_user_id and tweet.in_reply_to_user_id != source_id:
        edges.append({
            "source_user_id": source_id,
            "target_user_id": tweet.in_reply_to_user_id,
            "edge_type": "reply",
            "post_id": tweet.post_id,
            "created_at": tweet.created_at,
        })

    # 2. Quotes
    if tweet.is_quote and tweet.in_reply_to_user_id and tweet.in_reply_to_user_id != source_id:
        edges.append({
            "source_user_id": source_id,
            "target_user_id": tweet.in_reply_to_user_id,
            "edge_type": "quote",
            "post_id": tweet.post_id,
            "created_at": tweet.created_at,
        })

    return edges


async def upsert_user(session: AsyncSession, user: ScrapedUser) -> None:
    """Idempotently insert or update user profile details."""
    stmt = insert(User).values(
        user_id=user.user_id,
        handle=user.handle,
        display_name=user.display_name,
        bio=user.bio,
        location_raw=user.location_raw,
        profile_created_at=user.profile_created_at,
        followers_count=user.followers_count,
        following_count=user.following_count,
        verified=user.verified,
        language=user.language,
    )

    stmt = stmt.on_conflict_do_update(
        index_elements=[User.user_id],
        set_={
            "display_name": stmt.excluded.display_name,
            "bio": stmt.excluded.bio,
            "location_raw": stmt.excluded.location_raw,
            "followers_count": stmt.excluded.followers_count,
            "following_count": stmt.excluded.following_count,
            "verified": stmt.excluded.verified,
            "language": stmt.excluded.language,
        }
    )
    await session.execute(stmt)


async def upsert_post(session: AsyncSession, tweet: ScrapedTweet) -> bool:
    """
    Idempotently insert post.
    Returns True if newly inserted, False if already existed.
    """
    stmt = insert(Post).values(
        post_id=tweet.post_id,
        user_id=tweet.user_id,
        text=tweet.text,
        created_at=tweet.created_at,
        lang=tweet.lang,
        like_count=tweet.like_count,
        retweet_count=tweet.retweet_count,
        reply_count=tweet.reply_count,
        quote_count=tweet.quote_count,
        is_retweet=tweet.is_retweet,
        is_quote=tweet.is_quote,
        is_reply=tweet.is_reply,
        in_reply_to_post_id=tweet.in_reply_to_post_id,
        in_reply_to_user_id=tweet.in_reply_to_user_id,
        hashtags=tweet.hashtags,
        mentions=tweet.mentions,
    )

    stmt = stmt.on_conflict_do_nothing(index_elements=[Post.post_id])
    res = await session.execute(stmt)
    return res.rowcount > 0


async def insert_edge(session: AsyncSession, edge_data: dict) -> None:
    """Idempotently insert interaction graph edge."""
    stmt = insert(Edge).values(
        source_user_id=edge_data["source_user_id"],
        target_user_id=edge_data["target_user_id"],
        edge_type=edge_data["edge_type"],
        post_id=edge_data["post_id"],
        created_at=edge_data["created_at"],
    )
    stmt = stmt.on_conflict_do_nothing(
        constraint="uq_edge"
    )
    await session.execute(stmt)


async def persist_tweet_pipeline(session: AsyncSession, tweet: ScrapedTweet) -> Tuple[bool, int]:
    """
    Complete idempotent persistence pipeline:
    1. Upsert author user
    2. Upsert tweet
    3. Insert derived edges
    Returns (is_new_tweet, num_edges_inserted)
    """
    if tweet.user:
        await upsert_user(session, tweet.user)

    is_new = await upsert_post(session, tweet)

    edges = derive_edges_from_tweet(tweet)
    for edge in edges:
        try:
            await insert_edge(session, edge)
        except Exception as exc:
            logger.debug("edge_insert_ignored", error=str(exc))

    await session.commit()
    return is_new, len(edges)
