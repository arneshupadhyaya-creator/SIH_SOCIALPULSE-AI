"""Initial schema — all six tables + TimescaleDB hypertable

Revision ID: 001_initial
Revises: None
Create Date: 2026-09-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users ─────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("user_id", sa.BigInteger(), autoincrement=False,
                  nullable=False, comment="X/Twitter snowflake user ID"),
        sa.Column("handle", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("location_raw", sa.Text(), nullable=True,
                  comment="Free-text location from profile"),
        sa.Column("profile_created_at", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("followers_count", sa.Integer(), server_default="0"),
        sa.Column("following_count", sa.Integer(), server_default="0"),
        sa.Column("verified", sa.Boolean(), server_default="false"),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_users_handle", "users", ["handle"], unique=True)

    # ── posts (will become hypertable) ────────────────────────
    op.create_table(
        "posts",
        sa.Column("post_id", sa.BigInteger(), autoincrement=False,
                  nullable=False, comment="X/Twitter snowflake tweet ID"),
        sa.Column("user_id", sa.BigInteger(),
                  sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  comment="Partition column for TimescaleDB hypertable"),
        sa.Column("lang", sa.Text(), nullable=True),
        sa.Column("like_count", sa.Integer(), server_default="0"),
        sa.Column("retweet_count", sa.Integer(), server_default="0"),
        sa.Column("reply_count", sa.Integer(), server_default="0"),
        sa.Column("quote_count", sa.Integer(), server_default="0"),
        sa.Column("is_retweet", sa.Boolean(), server_default="false"),
        sa.Column("is_quote", sa.Boolean(), server_default="false"),
        sa.Column("is_reply", sa.Boolean(), server_default="false"),
        sa.Column("in_reply_to_post_id", sa.BigInteger(), nullable=True),
        sa.Column("in_reply_to_user_id", sa.BigInteger(), nullable=True),
        sa.Column("hashtags", postgresql.ARRAY(sa.Text()), server_default="{}"),
        sa.Column("mentions", postgresql.ARRAY(sa.Text()), server_default="{}"),
        sa.PrimaryKeyConstraint("post_id"),
    )
    op.create_index("ix_posts_user_id", "posts", ["user_id"])
    op.create_index("ix_posts_created_at", "posts", ["created_at"])

    # Convert posts to TimescaleDB hypertable
    op.execute(
        "SELECT create_hypertable('posts', 'created_at', "
        "migrate_data => true, if_not_exists => true);"
    )

    # ── sentiment_scores ──────────────────────────────────────
    op.create_table(
        "sentiment_scores",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("post_id", sa.BigInteger(),
                  sa.ForeignKey("posts.post_id"), nullable=False),
        sa.Column("sentiment_label", sa.Text(), nullable=False),
        sa.Column("sentiment_score", sa.Float(), nullable=False),
        sa.Column("emotion_label", sa.Text(), nullable=False,
                  comment="supportive|against|excited|anxious|sarcastic-flag|neutral|other"),
        sa.Column("emotion_score", sa.Float(), nullable=False),
        sa.Column("is_sarcastic_prob", sa.Float(), server_default="0.0",
                  comment="Probability [0,1] — NOT ground truth"),
        sa.Column("computed_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id"),
    )
    op.create_index("ix_sentiment_scores_post_id", "sentiment_scores",
                    ["post_id"])

    # ── demographics_inferred ─────────────────────────────────
    op.create_table(
        "demographics_inferred",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(),
                  sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("age_bracket", sa.Text(), server_default="unknown",
                  comment="<18, 18-24, 25-34, 35-44, 45-54, 55+, unknown"),
        sa.Column("age_confidence", sa.Float(), server_default="0.0"),
        sa.Column("geo_country", sa.Text(), server_default="unknown"),
        sa.Column("geo_confidence", sa.Float(), server_default="0.0"),
        sa.Column("language", sa.Text(), server_default="unknown"),
        sa.Column("profession_category", sa.Text(), server_default="other",
                  comment="student|tech|healthcare|finance|creator|government|other"),
        sa.Column("profession_confidence", sa.Float(), server_default="0.0"),
        sa.Column("inferred_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_demographics_inferred_user_id",
                    "demographics_inferred", ["user_id"])

    # ── trends ────────────────────────────────────────────────
    op.create_table(
        "trends",
        sa.Column("trend_id", sa.Integer(), autoincrement=True,
                  nullable=False),
        sa.Column("keyword_or_topic", sa.Text(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("volume", sa.Integer(), server_default="0"),
        sa.Column("growth_rate", sa.Float(), server_default="0.0",
                  comment="Rising score: normalized rate of volume change"),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("representative_post_ids",
                  postgresql.ARRAY(sa.BigInteger()), server_default="{}"),
        sa.PrimaryKeyConstraint("trend_id"),
    )
    op.create_index("ix_trends_window", "trends",
                    ["window_start", "window_end"])

    # ── edges ─────────────────────────────────────────────────
    op.create_table(
        "edges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_user_id", sa.BigInteger(),
                  sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("target_user_id", sa.BigInteger(),
                  sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("edge_type", sa.Text(), nullable=False,
                  comment="mention | reply | retweet | quote"),
        sa.Column("post_id", sa.BigInteger(),
                  sa.ForeignKey("posts.post_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_user_id", "target_user_id", "edge_type",
                            "post_id", name="uq_edge"),
    )
    op.create_index("ix_edges_source_target", "edges",
                    ["source_user_id", "target_user_id"])
    op.create_index("ix_edges_source_user_id", "edges", ["source_user_id"])
    op.create_index("ix_edges_target_user_id", "edges", ["target_user_id"])


def downgrade() -> None:
    op.drop_table("edges")
    op.drop_table("trends")
    op.drop_table("demographics_inferred")
    op.drop_table("sentiment_scores")
    op.drop_table("posts")
    op.drop_table("users")
