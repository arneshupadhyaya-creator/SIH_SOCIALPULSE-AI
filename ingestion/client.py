"""
Rate-limit and circuit-breaker aware X (Twitter) scraper client.

Uses `twscrape` as the primary unofficial scraping engine, wrapped behind
an abstract adapter interface (ScraperClient) so it can be swapped out later.

COMPLIANCE & ETHICS / TOS WARNING:
----------------------------------
This build uses an UNOFFICIAL scraper (twscrape, no X API keys) to pull public data.
This is a Terms-of-Service gray area: X does not license this method of access,
actively rate-limits/IP-bans scrapers, and breaks scraping libraries whenever it
changes internal GraphQL endpoints — this is a real fragility risk for a live demo.
Only public data is scraped; no private profiles, no login bypass, no CAPTCHA solving.

FALLBACK OPTION (Architecture note):
-----------------------------------
If twscrape's GraphQL approach gets blocked by X, an alternative adapter class
`PlaywrightScraperClient(ScraperClient)` can be implemented using headless Chromium
to render public search pages (e.g. x.com/search?q=...) directly. That approach
is slower and heavier, but harder for bot detection to fingerprint.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional

from config import get_settings
from ingestion.models import ScrapedTweet, ScrapedUser
from logging_config import get_logger

logger = get_logger("ingestion.client")


class CircuitBreakerOpenError(Exception):
    """Raised when the circuit breaker is active and requests are blocked."""
    pass


class CircuitBreaker:
    """
    Guards the scraper account pool against hammering into bans/429 cascades.

    If failure count exceeds threshold within a sliding window, trips the breaker
    into OPEN state and rejects/pauses calls until timeout expires.
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 300):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count: int = 0
        self.last_failure_time: float = 0.0
        self.state: str = "CLOSED"  # CLOSED, OPEN, HALF-OPEN

    def record_success(self) -> None:
        if self.state == "HALF-OPEN":
            logger.info("circuit_breaker_recovered", state="CLOSED")
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self, error_type: str = "general") -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        logger.warning(
            "circuit_breaker_failure_recorded",
            failure_count=self.failure_count,
            threshold=self.failure_threshold,
            error_type=error_type,
        )

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.critical(
                "CIRCUIT_BREAKER_TRIPPED_OPEN",
                msg="Scraper error threshold exceeded! Pausing all requests to avoid IP/account ban.",
                cooldown_seconds=self.recovery_timeout,
            )

    def can_execute(self) -> bool:
        if self.state == "CLOSED":
            return True

        elapsed = time.time() - self.last_failure_time
        if elapsed >= self.recovery_timeout:
            self.state = "HALF-OPEN"
            logger.info("circuit_breaker_half_open_testing", elapsed_seconds=elapsed)
            return True

        return False

    def status_dict(self) -> Dict[str, object]:
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "remaining_cooldown": max(0.0, self.recovery_timeout - (time.time() - self.last_failure_time))
            if self.state == "OPEN" else 0.0,
        }


class ScraperClient(ABC):
    """Abstract adapter interface for social data scrapers."""

    @abstractmethod
    async def initialize(self) -> bool:
        """Load credentials, verify pool availability."""
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        limit: int = 50,
        since: Optional[str] = None,
    ) -> AsyncGenerator[ScrapedTweet, None]:
        """Search public tweets matching a query."""
        pass

    @abstractmethod
    async def get_user(self, handle_or_id: str) -> Optional[ScrapedUser]:
        """Fetch public profile metadata for a user."""
        pass

    @abstractmethod
    def get_pool_status(self) -> Dict[str, object]:
        """Return current status of account pool and circuit breaker."""
        pass


class TwscrapeClient(ScraperClient):
    """
    twscrape implementation of ScraperClient.

    Loads credentials from accounts.txt into an accounts.db pool, rotates
    accounts automatically, adds randomized jitter between queries, and applies
    circuit breaker protection.
    """

    def __init__(self, accounts_file: Optional[str] = None, pool_db: str = "accounts.db"):
        settings = get_settings()
        self.accounts_file = Path(accounts_file or settings.accounts_file)
        self.pool_db = pool_db
        self.delay_min = settings.scrape_delay_min
        self.delay_max = settings.scrape_delay_max
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=settings.circuit_breaker_threshold,
            recovery_timeout=settings.circuit_breaker_timeout,
        )
        self._api = None
        self._initialized = False

    async def _get_api(self):
        if self._api is None:
            try:
                from twscrape import API
                self._api = API(self.pool_db)
            except ImportError:
                logger.error("twscrape_not_installed", hint="pip install twscrape")
                raise RuntimeError("twscrape is not installed in the active environment.")
        return self._api

    async def initialize(self) -> bool:
        """
        Loads accounts from accounts.txt and adds them to the pool.
        Logs loud warnings if the accounts file is missing or empty.
        """
        if not self.accounts_file.exists():
            logger.warning(
                "ACCOUNTS_FILE_MISSING",
                file=str(self.accounts_file),
                msg="accounts.txt is missing. System requires valid credentials for live scraping.",
            )
            return False

        lines = self.accounts_file.read_text(encoding="utf-8").strip().splitlines()
        valid_lines = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]

        if not valid_lines:
            logger.warning(
                "ACCOUNTS_FILE_EMPTY",
                file=str(self.accounts_file),
                msg="accounts.txt contains no active account entries.",
            )
            return False

        api = await self._get_api()
        added_count = 0

        for line in valid_lines:
            try:
                # Format 1: username:password:email:email_password:cookies=...
                # Format 2: username:password:email:email_password
                # Format 3: username:auth_token=...;ct0=...
                parts = line.split(":")
                cookies = None
                cookie_idx = -1
                for idx, p in enumerate(parts):
                    if p.startswith("cookies="):
                        cookies = p.replace("cookies=", "")
                        cookie_idx = idx
                        break
                    elif "auth_token=" in p:
                        cookies = p
                        cookie_idx = idx
                        break

                if cookies and cookie_idx == 1:
                    # Cookie format: username:cookies
                    u = parts[0]
                    await api.pool.add_account(u, "none", f"{u}@local.test", "none", cookies=cookies)
                    added_count += 1
                elif len(parts) >= 4:
                    u, p, e, ep = parts[0], parts[1], parts[2], parts[3]
                    await api.pool.add_account(u, p, e, ep, cookies=cookies)
                    added_count += 1
                else:
                    logger.warning("skipping_malformed_account_line", line=line[:10] + "...")
            except Exception as ex:
                logger.warning("account_add_error", error=str(ex))

        logger.info("account_pool_initialized", added_accounts=added_count, total_in_file=len(valid_lines))
        self._initialized = True
        return True

    def _parse_tweet(self, tweet_obj) -> ScrapedTweet:
        """Converts twscrape Tweet object to ScrapedTweet dataclass."""
        # Handle user object
        u_obj = getattr(tweet_obj, "user", None)
        user_model = None
        if u_obj:
            user_model = ScrapedUser(
                user_id=int(getattr(u_obj, "id", 0)),
                handle=getattr(u_obj, "username", "") or "",
                display_name=getattr(u_obj, "displayname", "") or "",
                bio=getattr(u_obj, "rawDescription", "") or getattr(u_obj, "description", "") or "",
                location_raw=getattr(u_obj, "location", "") or "",
                profile_created_at=getattr(u_obj, "created", None),
                followers_count=int(getattr(u_obj, "followersCount", 0) or 0),
                following_count=int(getattr(u_obj, "friendsCount", 0) or 0),
                verified=bool(getattr(u_obj, "verified", False)),
                language=getattr(u_obj, "lang", None),
            )

        # Extract hashtags and mentions
        hashtags = [h if isinstance(h, str) else getattr(h, "tag", str(h)) for h in getattr(tweet_obj, "hashtags", []) or []]
        mentions = [
            m if isinstance(m, str) else getattr(m, "username", str(m))
            for m in getattr(tweet_obj, "mentionedUsers", []) or []
        ]

        # Datetime normalization
        dt = getattr(tweet_obj, "date", None)
        if dt is None:
            dt = datetime.now(timezone.utc)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return ScrapedTweet(
            post_id=int(getattr(tweet_obj, "id", 0)),
            user_id=int(getattr(tweet_obj, "user", None).id if getattr(tweet_obj, "user", None) else 0),
            text=getattr(tweet_obj, "rawContent", None) or getattr(tweet_obj, "renderedContent", None) or getattr(tweet_obj, "content", "") or "",
            created_at=dt,
            lang=getattr(tweet_obj, "lang", None),
            like_count=int(getattr(tweet_obj, "likeCount", 0) or 0),
            retweet_count=int(getattr(tweet_obj, "retweetCount", 0) or 0),
            reply_count=int(getattr(tweet_obj, "replyCount", 0) or 0),
            quote_count=int(getattr(tweet_obj, "quoteCount", 0) or 0),
            is_retweet=bool(getattr(tweet_obj, "retweetedTweet", None)),
            is_quote=bool(getattr(tweet_obj, "quotedTweet", None)),
            is_reply=bool(getattr(tweet_obj, "inReplyToTweetId", None)),
            in_reply_to_post_id=int(getattr(tweet_obj, "inReplyToTweetId", 0)) if getattr(tweet_obj, "inReplyToTweetId", None) else None,
            in_reply_to_user_id=int(getattr(tweet_obj, "inReplyToUserId", 0)) if getattr(tweet_obj, "inReplyToUserId", None) else None,
            hashtags=hashtags,
            mentions=mentions,
            user=user_model,
        )

    async def search(
        self,
        query: str,
        limit: int = 50,
        since: Optional[str] = None,
    ) -> AsyncGenerator[ScrapedTweet, None]:
        if not self.circuit_breaker.can_execute():
            raise CircuitBreakerOpenError(
                f"Circuit breaker is OPEN. Requests paused for {self.circuit_breaker.recovery_timeout}s."
            )

        api = await self._get_api()
        # Reset locks to avoid 15-minute wait stalls on single-account pools
        try:
            await api.pool.reset_locks()
        except Exception:
            pass

        final_query = query
        if since:
            final_query = f"{query} since:{since}"

        yielded = 0
        try:
            from twscrape import gather
            raw_tweets = await gather(api.search(final_query, limit=limit))
            for tweet in raw_tweets:
                if yielded >= limit:
                    break
                scraped = self._parse_tweet(tweet)
                yield scraped
                yielded += 1

            self.circuit_breaker.record_success()

            # Randomized jitter delay between search requests
            jitter = random.uniform(self.delay_min, self.delay_max)
            await asyncio.sleep(jitter)

        except Exception as exc:
            self.circuit_breaker.record_failure(error_type=type(exc).__name__)
            logger.error("search_failed", query=query, error=str(exc))
            raise

    async def get_user(self, handle_or_id: str) -> Optional[ScrapedUser]:
        if not self.circuit_breaker.can_execute():
            raise CircuitBreakerOpenError("Circuit breaker is OPEN.")

        api = await self._get_api()
        try:
            u_obj = await api.user_by_login(handle_or_id) if not handle_or_id.isdigit() else await api.user_by_id(int(handle_or_id))
            if not u_obj:
                return None

            self.circuit_breaker.record_success()
            return ScrapedUser(
                user_id=int(getattr(u_obj, "id", 0)),
                handle=getattr(u_obj, "username", "") or "",
                display_name=getattr(u_obj, "displayname", "") or "",
                bio=getattr(u_obj, "rawDescription", "") or getattr(u_obj, "description", "") or "",
                location_raw=getattr(u_obj, "location", "") or "",
                profile_created_at=getattr(u_obj, "created", None),
                followers_count=int(getattr(u_obj, "followersCount", 0) or 0),
                following_count=int(getattr(u_obj, "friendsCount", 0) or 0),
                verified=bool(getattr(u_obj, "verified", False)),
                language=getattr(u_obj, "lang", None),
            )
        except Exception as exc:
            self.circuit_breaker.record_failure(error_type=type(exc).__name__)
            logger.error("get_user_failed", user=handle_or_id, error=str(exc))
            return None

    def get_pool_status(self) -> Dict[str, object]:
        return {
            "initialized": self._initialized,
            "accounts_file": str(self.accounts_file),
            "accounts_file_exists": self.accounts_file.exists(),
            "circuit_breaker": self.circuit_breaker.status_dict(),
        }
