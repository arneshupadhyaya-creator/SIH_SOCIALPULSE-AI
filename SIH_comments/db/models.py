"""
SQLAlchemy ORM models for the Audience Intelligence data layer.

Tables
------
- users          — scraped X profiles
- posts          — scraped tweets (TimescaleDB hypertable on created_at)
- sentiment_scores   — per-post sentiment + emotion scores
- demographics_inferred — per-user inferred demographics
- trends         — sliding-window trend snapshots
- edges          — directed interaction graph (mention/reply/RT/quote)

Design notes
~~~~~~~~~~~~
* ``posts`` is converted to a TimescaleDB hypertable after creation via a
  SQLAlchemy ``after_create`` DDL event — see bottom of this file.
* ARRAY columns (hashtags, mentions, representative_post_ids) use
  ``postgresql.ARRAY(Text)`` — Postgres-native arrays.
* All FK relationships use ``BigInteger`` to match X/Twitter snowflake IDs.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    DDL,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, relationship


# ── Base ──────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """Shared declarative base for all models."""
    pass


# ── Users ─────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    user_id = Column(BigInteger, primary_key=True, autoincrement=False,
                     comment="X/Twitter snowflake user ID")
    handle = Column(Text, nullable=False, index=True, unique=True)
    display_name = Column(Text)
    bio = Column(Text)
    location_raw = Column(Text, comment="Free-text location from profile")
    profile_created_at = Column(DateTime(timezone=True))
    followers_count = Column(Integer, default=0)
    following_count = Column(Integer, default=0)
    verified = Column(Boolean, default=False)
    language = Column(Text)
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(),
                          onupdate=func.now())

    # Relationships
    posts = relationship("Post", back_populates="user", lazy="dynamic")
    demographics = relationship("DemographicsInferred", back_populates="user",
                                uselist=False, lazy="joined")


# ── Posts (TimescaleDB hypertable) ────────────────────────────
class Post(Base):
    __tablename__ = "posts"

    post_id = Column(BigInteger, primary_key=True, autoincrement=False,
                     comment="X/Twitter snowflake tweet ID")
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False,
                     index=True)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, index=True,
                        comment="Partition column for TimescaleDB hypertable")
    lang = Column(Text)
    like_count = Column(Integer, default=0)
    retweet_count = Column(Integer, default=0)
    reply_count = Column(Integer, default=0)
    quote_count = Column(Integer, default=0)

    is_retweet = Column(Boolean, default=False)
    is_quote = Column(Boolean, default=False)
    is_reply = Column(Boolean, default=False)
    in_reply_to_post_id = Column(BigInteger, nullable=True)
    in_reply_to_user_id = Column(BigInteger, nullable=True)

    hashtags = Column(ARRAY(Text), default=[])
    mentions = Column(ARRAY(Text), default=[])

    # Relationships
    user = relationship("User", back_populates="posts")
    sentiment = relationship("SentimentScore", back_populates="post",
                             uselist=False, lazy="joined")


# ── Sentiment Scores ─────────────────────────────────────────
class SentimentScore(Base):
    __tablename__ = "sentiment_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(BigInteger, ForeignKey("posts.post_id"), nullable=False,
                     unique=True, index=True)

    # Base sentiment (positive / negative / neutral)
    sentiment_label = Column(Text, nullable=False)
    sentiment_score = Column(Float, nullable=False)

    # Nuanced emotion from ML classifier / ensemble
    emotion_label = Column(Text, nullable=False,
                           comment="Emotion categories: happiness, enthusiasm, fun, love, relief, "
                                   "surprise, sadness, worry, anger, hate, boredom, empty, neutral, sarcastic-flag")
    emotion_score = Column(Float, nullable=False)


    # Sarcasm probability (ensemble: model + rule-based cues)
    is_sarcastic_prob = Column(Float, default=0.0,
                               comment="Probability [0,1] — NOT ground truth")

    computed_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    post = relationship("Post", back_populates="sentiment")


# ── Demographics (inferred, per-user) ────────────────────────
class DemographicsInferred(Base):
    __tablename__ = "demographics_inferred"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False,
                     unique=True, index=True)

    age_bracket = Column(Text, default="unknown",
                         comment="<18, 18-24, 25-34, 35-44, 45-54, 55+, unknown")
    age_confidence = Column(Float, default=0.0)

    geo_country = Column(Text, default="unknown")
    geo_confidence = Column(Float, default=0.0)

    language = Column(Text, default="unknown")

    profession_category = Column(Text, default="other",
                                 comment="student, tech, healthcare, finance, "
                                         "creator, government, other")
    profession_confidence = Column(Float, default=0.0)

    inferred_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="demographics")


# ── Trends ────────────────────────────────────────────────────
class Trend(Base):
    __tablename__ = "trends"

    trend_id = Column(Integer, primary_key=True, autoincrement=True)
    keyword_or_topic = Column(Text, nullable=False)
    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False)
    volume = Column(Integer, default=0)
    growth_rate = Column(Float, default=0.0,
                         comment="Rising score: normalized rate of volume change")
    rank = Column(Integer, nullable=True)
    representative_post_ids = Column(ARRAY(BigInteger), default=[])

    __table_args__ = (
        Index("ix_trends_window", "window_start", "window_end"),
    )


# ── Edges (interaction graph) ────────────────────────────────
class Edge(Base):
    __tablename__ = "edges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_user_id = Column(BigInteger, ForeignKey("users.user_id"),
                            nullable=False, index=True)
    target_user_id = Column(BigInteger, ForeignKey("users.user_id"),
                            nullable=False, index=True)
    edge_type = Column(Text, nullable=False,
                       comment="mention | reply | retweet | quote")
    post_id = Column(BigInteger, ForeignKey("posts.post_id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_edges_source_target", "source_user_id", "target_user_id"),
        UniqueConstraint("source_user_id", "target_user_id", "edge_type",
                         "post_id", name="uq_edge"),
    )


# ── TimescaleDB hypertable conversion ────────────────────────
# After SQLAlchemy creates the `posts` table, convert it to a hypertable.
# This runs only on initial table creation, not on every app start.
# For Alembic migrations, the same DDL is included in the migration file.
_hypertable_ddl = DDL(
    "SELECT create_hypertable('posts', 'created_at', "
    "migrate_data => true, if_not_exists => true);"
)
event.listen(Post.__table__, "after_create", _hypertable_ddl)
