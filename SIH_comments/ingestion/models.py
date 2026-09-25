"""
Internal dataclasses for scraped entities.

Decouples twscrape's internal data representation from the rest of the application.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class ScrapedUser:
    user_id: int
    handle: str
    display_name: Optional[str] = None
    bio: Optional[str] = None
    location_raw: Optional[str] = None
    profile_created_at: Optional[datetime] = None
    followers_count: int = 0
    following_count: int = 0
    verified: bool = False
    language: Optional[str] = None


@dataclass
class ScrapedTweet:
    post_id: int
    user_id: int
    text: str
    created_at: datetime
    lang: Optional[str] = None
    like_count: int = 0
    retweet_count: int = 0
    reply_count: int = 0
    quote_count: int = 0
    is_retweet: bool = False
    is_quote: bool = False
    is_reply: bool = False
    in_reply_to_post_id: Optional[int] = None
    in_reply_to_user_id: Optional[int] = None
    hashtags: List[str] = field(default_factory=list)
    mentions: List[str] = field(default_factory=list)
    user: Optional[ScrapedUser] = None


@dataclass
class ScrapedEdge:
    source_user_id: int
    target_user_id: int
    edge_type: str  # mention | reply | retweet | quote
    post_id: int
    created_at: datetime
