"""
Unit & Integration tests for Tweet Comment / Reply Scraping functionality.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion.client import ScraperClient, TwscrapeClient
from ingestion.models import ScrapedTweet, ScrapedUser
from ingestion.store import derive_edges_from_tweet, ensure_user_stub, persist_tweet_pipeline


def test_scraper_client_interface():
    """Verify ScraperClient defines get_replies."""
    assert hasattr(ScraperClient, "get_replies")
    assert hasattr(TwscrapeClient, "get_replies")
    print("[TEST 1: Interface] TwscrapeClient has get_replies method.")


def test_parse_tweet_with_replies():
    """Verify _parse_tweet accurately extracts inReplyToTweetId and inReplyToUser."""
    client = TwscrapeClient()

    # Create dummy twscrape Tweet-like object
    class DummyUserRef:
        id = 99887766
        username = "original_poster"

    class DummyUser:
        id = 11223344
        username = "commenter"
        displayname = "Helpful Commenter"
        rawDescription = "I comment on things"
        location = "Internet"
        created = datetime.now(timezone.utc)
        followersCount = 50
        friendsCount = 100
        verified = True
        lang = "en"

    class DummyTweet:
        id = 5544332211
        user = DummyUser()
        rawContent = "This is a great comment on your post!"
        date = datetime.now(timezone.utc)
        lang = "en"
        likeCount = 12
        retweetCount = 2
        replyCount = 0
        quoteCount = 0
        retweetedTweet = None
        quotedTweet = None
        inReplyToTweetId = 1234567890
        inReplyToUser = DummyUserRef()
        hashtags = ["discussion"]
        mentionedUsers = []

    parsed = client._parse_tweet(DummyTweet())
    assert parsed.post_id == 5544332211
    assert parsed.is_reply is True
    assert parsed.in_reply_to_post_id == 1234567890
    assert parsed.in_reply_to_user_id == 99887766
    assert parsed.user.handle == "commenter"
    print(f"[TEST 2: Parsing] Parsed reply comment: post_id={parsed.post_id}, parent_id={parsed.in_reply_to_post_id}, target_user={parsed.in_reply_to_user_id}")


def test_reply_edge_derivation():
    """Verify reply comments produce directed interaction edges in the graph."""
    comment = ScrapedTweet(
        post_id=5544332211,
        user_id=11223344,
        text="Insightful commentary!",
        created_at=datetime.now(timezone.utc),
        is_reply=True,
        in_reply_to_post_id=1234567890,
        in_reply_to_user_id=99887766,
    )

    edges = derive_edges_from_tweet(comment)
    assert len(edges) == 1
    edge = edges[0]
    assert edge["source_user_id"] == 11223344
    assert edge["target_user_id"] == 99887766
    assert edge["edge_type"] == "reply"
    assert edge["post_id"] == 5544332211
    print(f"[TEST 3: Edge Derivation] Derived reply edge: {edge['source_user_id']} -> {edge['target_user_id']} (type={edge['edge_type']})")


def test_fastapi_endpoints_registered():
    """Verify comments scraping endpoints are registered on FastAPI app."""
    from api.main import app

    routes = [r.path for r in app.routes]
    assert "/api/scraper/comments" in routes
    assert "/api/posts/{post_id}/comments" in routes
    assert "/api/scraper/test" in routes
    assert "/api/scraper/test-full" in routes
    assert "/ingest/run" in routes
    print("[TEST 4: API Routes] /api/scraper/comments and /api/posts/{post_id}/comments are registered.")


def test_fastapi_request_schemas():
    """Verify request schemas have comment scraping parameters."""
    from api.main import ScraperTestRequest, IngestRunRequest, PostCommentsRequest

    test_req = ScraperTestRequest(query="AI", scrape_comments=True, comments_limit=8)
    assert test_req.scrape_comments is True
    assert test_req.comments_limit == 8

    ingest_req = IngestRunRequest(query="AI", scrape_comments=True, comments_limit=15)
    assert ingest_req.scrape_comments is True
    assert ingest_req.comments_limit == 15

    post_comm_req = PostCommentsRequest(post_id=123456, limit=10)
    assert post_comm_req.post_id == 123456
    assert post_comm_req.limit == 10
    print("[TEST 5: Schemas] ScraperTestRequest, IngestRunRequest, and PostCommentsRequest validate properly.")


if __name__ == "__main__":
    test_scraper_client_interface()
    test_parse_tweet_with_replies()
    test_reply_edge_derivation()
    test_fastapi_endpoints_registered()
    test_fastapi_request_schemas()
    print("\nALL COMMENT SCRAPING TESTS PASSED SUCCESSFULLY!")
