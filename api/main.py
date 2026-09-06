"""
FastAPI main application entrypoint.

Exposes:
- Web Test Studio: GET / (interactive UI for testing the scraper)
- Scraper Testing API:
    GET  /api/scraper/status
    POST /api/scraper/test
    GET  /api/scraper/accounts
    POST /api/scraper/accounts
- System & Stage 1 Endpoints:
    GET  /health
    POST /ingest/run
    GET  /sentiment/timeline
    GET  /demographics/summary
    GET  /trends/current
    GET  /network/influencers
    GET  /network/communities
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import get_settings
from ingestion.client import CircuitBreakerOpenError, TwscrapeClient
from ingestion.store import derive_edges_from_tweet
from logging_config import get_logger, setup_logging

setup_logging()
logger = get_logger("api.main")
settings = get_settings()

# Global scraper client instance
scraper_client = TwscrapeClient()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("app_starting", host=settings.api_host, port=settings.api_port)
    # Initialize scraper pool if accounts.txt exists
    try:
        await scraper_client.initialize()
    except Exception as ex:
        logger.warning("scraper_client_init_notice", error=str(ex))
    yield
    logger.info("app_stopping")


app = FastAPI(
    title="Social Media Audience Intelligence API & Scraper Studio",
    version="1.0.0",
    description="Stage 1: Production-quality public X audience intelligence vertical slice",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for web studio
web_dir = Path(__file__).resolve().parent.parent / "web"
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")


# ── Schemas ───────────────────────────────────────────────────
class ScraperTestRequest(BaseModel):
    query: str = Field(..., description="Keyword, hashtag, or handle to search")
    limit: int = Field(10, ge=1, le=50, description="Max tweets to fetch")
    since: Optional[str] = Field(None, description="Since date (YYYY-MM-DD)")


class IngestRunRequest(BaseModel):
    mode: str = Field("search", description="Mode: 'search' or 'poll'")
    query: str = Field(..., description="Keyword or hashtag")
    since: Optional[str] = Field(None, description="Since date (YYYY-MM-DD)")
    limit: int = Field(50, ge=1, le=200)


class AccountsUpdateRequest(BaseModel):
    content: str


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_index():
    index_path = web_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Scraper Test Studio UI: index.html not found"}


# ── System Endpoints ──────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health():
    return {
        "status": "ok",
        "stage": 1,
        "platform": "x",
        "scraper": "twscrape",
        "circuit_breaker": scraper_client.circuit_breaker.state,
    }


# ── Scraper Studio Endpoints ──────────────────────────────────
@app.get("/api/scraper/status", tags=["Scraper Studio"])
async def get_scraper_status():
    status = scraper_client.get_pool_status()
    acc_path = Path(settings.accounts_file)
    count = 0
    if acc_path.exists():
        lines = [l.strip() for l in acc_path.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
        count = len(lines)
    status["account_count"] = count
    return status


@app.post("/api/scraper/test", tags=["Scraper Studio"])
async def run_scraper_test(req: ScraperTestRequest):
    """
    Executes a live search query using the unofficial twscrape client.
    Returns scraped tweet objects, extracted entities, derived edges, and latency.
    """
    acc_path = Path(settings.accounts_file)
    if not acc_path.exists():
        raise HTTPException(
            status_code=400,
            detail="accounts.txt is missing. The system requires an account pool to scrape public X data without official API keys."
        )

    # Ensure client is initialized
    await scraper_client.initialize()

    tweets_data = []
    edges_data = []

    try:
        async for tweet in scraper_client.search(query=req.query, limit=req.limit, since=req.since):
            # Format tweet
            tweet_dict = {
                "post_id": tweet.post_id,
                "user_id": tweet.user_id,
                "text": tweet.text,
                "created_at": tweet.created_at.isoformat() if tweet.created_at else None,
                "lang": tweet.lang,
                "like_count": tweet.like_count,
                "retweet_count": tweet.retweet_count,
                "reply_count": tweet.reply_count,
                "quote_count": tweet.quote_count,
                "is_retweet": tweet.is_retweet,
                "is_quote": tweet.is_quote,
                "is_reply": tweet.is_reply,
                "hashtags": tweet.hashtags,
                "mentions": tweet.mentions,
                "user": {
                    "user_id": tweet.user.user_id,
                    "handle": tweet.user.handle,
                    "display_name": tweet.user.display_name,
                    "bio": tweet.user.bio,
                    "location_raw": tweet.user.location_raw,
                    "followers_count": tweet.user.followers_count,
                    "following_count": tweet.user.following_count,
                    "verified": tweet.user.verified,
                } if tweet.user else None
            }
            tweets_data.append(tweet_dict)

            # Derive edges
            derived = derive_edges_from_tweet(tweet)
            for e in derived:
                edges_data.append({
                    "source_user_id": e["source_user_id"],
                    "target_user_id": e["target_user_id"],
                    "edge_type": e["edge_type"],
                    "post_id": e["post_id"],
                    "created_at": e["created_at"].isoformat() if hasattr(e["created_at"], "isoformat") else str(e["created_at"])
                })

        return {
            "status": "success",
            "query": req.query,
            "count": len(tweets_data),
            "tweets": tweets_data,
            "edges": edges_data,
            "circuit_breaker": scraper_client.circuit_breaker.status_dict(),
        }

    except CircuitBreakerOpenError as cb_err:
        raise HTTPException(status_code=429, detail=str(cb_err))
    except Exception as ex:
        logger.error("scraper_test_error", error=str(ex))
        raise HTTPException(status_code=500, detail=f"Scraper execution error: {str(ex)}")


@app.get("/api/scraper/accounts", tags=["Scraper Studio"])
async def get_accounts_content():
    acc_path = Path(settings.accounts_file)
    if not acc_path.exists():
        example_path = Path("accounts.example.txt")
        content = example_path.read_text(encoding="utf-8") if example_path.exists() else ""
        return {"exists": False, "content": content}
    return {"exists": True, "content": acc_path.read_text(encoding="utf-8")}


@app.post("/api/scraper/accounts", tags=["Scraper Studio"])
async def update_accounts_content(req: AccountsUpdateRequest):
    acc_path = Path(settings.accounts_file)
    acc_path.write_text(req.content.strip() + "\n", encoding="utf-8")
    # Reinitialize pool
    reloaded = await scraper_client.initialize()
    return {"status": "saved", "reloaded": reloaded, "message": "accounts.txt updated successfully"}


# ── Stage 1 Pipeline Ingest Endpoint ──────────────────────────
@app.post("/ingest/run", tags=["Ingestion"])
async def trigger_ingest(req: IngestRunRequest, background_tasks: BackgroundTasks):
    """
    Triggers an asynchronous scraping run over a keyword/hashtag.
    """
    from ingestion.run import run_search
    background_tasks.add_task(run_search, req.query, req.limit, req.since)
    return {
        "status": "accepted",
        "mode": req.mode,
        "query": req.query,
        "limit": req.limit,
        "message": f"Ingestion job started in background for query '{req.query}'",
    }


# ── Sentiment Analysis Endpoints ──────────────────────────────
class SentimentAnalyzeRequest(BaseModel):
    texts: List[str] = Field(..., description="List of tweet texts to analyze")


@app.post("/api/sentiment/analyze", tags=["Sentiment"])
async def analyze_sentiment(req: SentimentAnalyzeRequest):
    """
    Run the ensemble sentiment + emotion + sarcasm pipeline on provided texts.
    Returns per-text results with base sentiment, nuanced emotion, and sarcasm probability.
    """
    try:
        from analytics.sentiment import get_sentiment_engine
        engine = get_sentiment_engine(device=settings.device)
        results = engine.score_batch(req.texts)
        return {
            "status": "success",
            "count": len(results),
            "results": [
                {
                    "text": text[:200],
                    "sentiment_label": r.sentiment_label,
                    "sentiment_score": r.sentiment_score,
                    "emotion_label": r.emotion_label,
                    "emotion_score": r.emotion_score,
                    "is_sarcastic_prob": r.is_sarcastic_prob,
                }
                for text, r in zip(req.texts, results)
            ],
        }
    except Exception as ex:
        logger.error("sentiment_analyze_error", error=str(ex))
        raise HTTPException(status_code=500, detail=f"Sentiment analysis error: {str(ex)}")


@app.post("/api/scraper/test-full", tags=["Scraper Studio"])
async def run_scraper_test_full(req: ScraperTestRequest):
    """
    Executes a live scrape AND runs sentiment + demographics analysis on the results.
    Returns tweets with sentiment scores, edges, and aggregated demographics.
    """
    acc_path = Path(settings.accounts_file)
    if not acc_path.exists():
        raise HTTPException(
            status_code=400,
            detail="accounts.txt is missing."
        )

    await scraper_client.initialize()

    tweets_data = []
    edges_data = []
    tweet_texts = []
    user_profiles = []

    try:
        async for tweet in scraper_client.search(query=req.query, limit=req.limit, since=req.since):
            tweet_dict = {
                "post_id": tweet.post_id,
                "user_id": tweet.user_id,
                "text": tweet.text,
                "created_at": tweet.created_at.isoformat() if tweet.created_at else None,
                "lang": tweet.lang,
                "like_count": tweet.like_count,
                "retweet_count": tweet.retweet_count,
                "reply_count": tweet.reply_count,
                "quote_count": tweet.quote_count,
                "is_retweet": tweet.is_retweet,
                "is_quote": tweet.is_quote,
                "is_reply": tweet.is_reply,
                "hashtags": tweet.hashtags,
                "mentions": tweet.mentions,
                "user": {
                    "user_id": tweet.user.user_id,
                    "handle": tweet.user.handle,
                    "display_name": tweet.user.display_name,
                    "bio": tweet.user.bio,
                    "location_raw": tweet.user.location_raw,
                    "followers_count": tweet.user.followers_count,
                    "following_count": tweet.user.following_count,
                    "verified": tweet.user.verified,
                } if tweet.user else None
            }
            tweets_data.append(tweet_dict)
            tweet_texts.append(tweet.text)

            if tweet.user:
                user_profiles.append({
                    "bio": tweet.user.bio,
                    "location_raw": tweet.user.location_raw,
                })

            derived = derive_edges_from_tweet(tweet)
            for e in derived:
                edges_data.append({
                    "source_user_id": e["source_user_id"],
                    "target_user_id": e["target_user_id"],
                    "edge_type": e["edge_type"],
                    "post_id": e["post_id"],
                    "created_at": e["created_at"].isoformat() if hasattr(e["created_at"], "isoformat") else str(e["created_at"])
                })

        # Run Sentiment Analysis
        sentiment_results = []
        try:
            from analytics.sentiment import get_sentiment_engine
            engine = get_sentiment_engine(device=settings.device)
            for i, text in enumerate(tweet_texts):
                result = engine.score_text(text)
                tweets_data[i]["sentiment"] = {
                    "label": result.sentiment_label,
                    "score": result.sentiment_score,
                    "emotion": result.emotion_label,
                    "emotion_score": result.emotion_score,
                    "sarcasm_prob": result.is_sarcastic_prob,
                    "detected_language": result.detected_language,
                    "translated_text": result.translated_text,
                }
                sentiment_results.append(result)

        except Exception as ex:
            logger.warning("sentiment_analysis_skipped", error=str(ex))

        # Compute sentiment aggregation
        sentiment_summary = {}
        if sentiment_results:
            from collections import Counter
            sent_counts = Counter(r.sentiment_label for r in sentiment_results)
            emo_counts = Counter(r.emotion_label for r in sentiment_results)
            total = len(sentiment_results)
            avg_sarcasm = sum(r.is_sarcastic_prob for r in sentiment_results) / total
            sentiment_summary = {
                "total_analyzed": total,
                "sentiment_mix": {
                    k: {"count": v, "percentage": round(v / total * 100, 1)}
                    for k, v in sent_counts.most_common()
                },
                "emotion_mix": {
                    k: {"count": v, "percentage": round(v / total * 100, 1)}
                    for k, v in emo_counts.most_common()
                },
                "avg_sarcasm_probability": round(avg_sarcasm, 4),
            }

        # Run Demographics Analysis (aggregated only — no per-user exposure)
        demographics_summary = {}
        try:
            from analytics.demographics import get_demographics_engine, aggregate_demographics
            demo_engine = get_demographics_engine(device=settings.device)
            demo_results = demo_engine.infer_batch(user_profiles)
            demographics_summary = aggregate_demographics(demo_results)
        except Exception as ex:
            logger.warning("demographics_analysis_skipped", error=str(ex))

        # Run Real-Time Trend & Topic Detection
        trend_summary = {}
        try:
            from analytics.trends import get_trend_engine
            trend_engine = get_trend_engine()
            t_res = trend_engine.analyze_stream(tweets_data)
            trend_summary = {
                "total_posts": t_res.total_posts,
                "analyzed_window_hours": t_res.analyzed_window_hours,
                "rising_trends": [
                    {
                        "keyword": t.keyword_or_topic,
                        "is_hashtag": t.is_hashtag,
                        "volume": t.total_volume,
                        "growth_rate": t.growth_rate,
                        "acceleration": t.acceleration,
                        "virality_score": t.virality_score,
                        "status": t.virality_status,
                        "reach": t.engagement_reach,
                    }
                    for t in t_res.rising_trends
                ],
                "predicted_viral_topics": [
                    {
                        "keyword": t.keyword_or_topic,
                        "is_hashtag": t.is_hashtag,
                        "virality_score": t.virality_score,
                        "growth_rate": t.growth_rate,
                        "status": t.virality_status,
                        "volume": t.total_volume,
                    }
                    for t in t_res.predicted_viral_topics
                ],
                "topic_clusters": [
                    {
                        "topic_id": c.topic_id,
                        "label": c.topic_label,
                        "top_terms": c.top_terms,
                        "volume": c.volume,
                        "growth_rate": c.growth_rate,
                        "sentiment_distribution": c.sentiment_distribution,
                        "sample_snippets": c.sample_snippets,
                    }
                    for c in t_res.topic_clusters
                ],
                "chronological_shifts": t_res.chronological_shifts,
            }
        except Exception as ex:
            logger.warning("trend_analysis_skipped", error=str(ex))

        # Run Link Analysis & Network Topology
        network_summary = {}
        try:
            from analytics.network import get_network_engine
            net_engine = get_network_engine()
            n_res = net_engine.build_and_analyze(tweets_data, edges_data)
            network_summary = {
                "total_nodes": n_res.total_nodes,
                "total_edges": n_res.total_edges,
                "graph_density": n_res.graph_density,
                "nodes": n_res.nodes,
                "links": n_res.links,
                "influencers": [
                    {
                        "user_id": inf.user_id,
                        "handle": inf.handle,
                        "display_name": inf.display_name,
                        "followers_count": inf.followers_count,
                        "influence_score": inf.influence_score,
                        "archetype": inf.archetype,
                        "pagerank": inf.pagerank,
                        "in_degree": inf.in_degree,
                        "out_degree": inf.out_degree,
                        "betweenness": inf.betweenness,
                        "community_id": inf.community_id,
                        "dominant_sentiment": inf.dominant_sentiment,
                        "verified": inf.verified,
                    }
                    for inf in n_res.influencers
                ],
                "communities": [
                    {
                        "community_id": c.community_id,
                        "label": c.label,
                        "color": c.color,
                        "member_count": c.member_count,
                        "top_influencers": c.top_influencers,
                        "dominant_sentiment": c.dominant_sentiment,
                        "sentiment_breakdown": c.sentiment_breakdown,
                    }
                    for c in n_res.communities
                ],
                "spread_cascade": [
                    {
                        "step": s.step_order,
                        "source": s.source_handle,
                        "target": s.target_handle,
                        "edge_type": s.edge_type,
                        "from_segment": s.from_segment,
                        "to_segment": s.to_segment,
                        "snippet": s.post_snippet,
                        "sentiment": s.sentiment_tone,
                        "timestamp": s.timestamp,
                    }
                    for s in n_res.spread_cascade
                ],
            }
        except Exception as ex:
            logger.warning("network_analysis_skipped", error=str(ex))

        # Cache session results
        global _latest_trend_summary, _latest_network_summary
        _latest_trend_summary = trend_summary
        _latest_network_summary = network_summary

        return {
            "status": "success",
            "query": req.query,
            "count": len(tweets_data),
            "tweets": tweets_data,
            "edges": edges_data,
            "sentiment_summary": sentiment_summary,
            "demographics_summary": demographics_summary,
            "trend_summary": trend_summary,
            "network_summary": network_summary,
            "circuit_breaker": scraper_client.circuit_breaker.status_dict(),
        }

    except CircuitBreakerOpenError as cb_err:
        raise HTTPException(status_code=429, detail=str(cb_err))
    except Exception as ex:
        logger.error("scraper_test_full_error", error=str(ex))
        raise HTTPException(status_code=500, detail=f"Full analysis error: {str(ex)}")


# Session caches for quick query endpoints
_latest_trend_summary: dict = {}
_latest_network_summary: dict = {}


# ── Demographics Endpoints ────────────────────────────────────
class DemographicsAnalyzeRequest(BaseModel):
    users: List[dict] = Field(..., description="List of user dicts with 'bio' and 'location_raw' keys")


@app.post("/api/demographics/analyze", tags=["Demographics"])
async def analyze_demographics(req: DemographicsAnalyzeRequest):
    """
    Run demographics inference on provided user profiles.
    Returns ONLY aggregated cohort-level counts — never per-user data.
    """
    try:
        from analytics.demographics import get_demographics_engine, aggregate_demographics
        engine = get_demographics_engine(device=settings.device)
        results = engine.infer_batch(req.users)
        aggregated = aggregate_demographics(results)
        return {
            "status": "success",
            **aggregated,
        }
    except Exception as ex:
        logger.error("demographics_analyze_error", error=str(ex))
        raise HTTPException(status_code=500, detail=f"Demographics analysis error: {str(ex)}")


# ── Trend & Topic Detection Endpoints ─────────────────────────
class TrendAnalyzeRequest(BaseModel):
    tweets: List[dict] = Field(..., description="List of tweet objects with text, created_at, likes, etc.")


@app.post("/api/trends/detect", tags=["Trends"])
async def detect_trends(req: TrendAnalyzeRequest):
    """
    Analyzes tweets chronologically to extract rising trends, viral predictions,
    topic clusters, and temporal shifts.
    """
    try:
        from analytics.trends import get_trend_engine
        engine = get_trend_engine()
        result = engine.analyze_stream(req.tweets)
        return {
            "status": "success",
            "rising_trends": [
                {
                    "keyword": t.keyword_or_topic,
                    "is_hashtag": t.is_hashtag,
                    "volume": t.total_volume,
                    "growth_rate": t.growth_rate,
                    "acceleration": t.acceleration,
                    "virality_score": t.virality_score,
                    "status": t.virality_status,
                }
                for t in result.rising_trends
            ],
            "predicted_viral_topics": [
                {
                    "keyword": t.keyword_or_topic,
                    "virality_score": t.virality_score,
                    "growth_rate": t.growth_rate,
                    "status": t.virality_status,
                }
                for t in result.predicted_viral_topics
            ],
            "topic_clusters": [
                {
                    "topic_id": c.topic_id,
                    "label": c.topic_label,
                    "top_terms": c.top_terms,
                    "volume": c.volume,
                    "sentiment_distribution": c.sentiment_distribution,
                    "sample_snippets": c.sample_snippets,
                }
                for c in result.topic_clusters
            ],
            "chronological_shifts": result.chronological_shifts,
        }
    except Exception as ex:
        logger.error("trend_detect_error", error=str(ex))
        raise HTTPException(status_code=500, detail=f"Trend detection error: {str(ex)}")


@app.get("/trends/current", tags=["Trends"])
async def get_current_trends():
    """
    Returns current rising trends and predicted viral topics from the latest active session.
    """
    global _latest_trend_summary
    if _latest_trend_summary:
        return {"status": "success", **_latest_trend_summary}
    return {
        "status": "empty",
        "message": "No trends computed yet. Run a search query in the Studio to generate trends.",
        "rising_trends": [],
        "predicted_viral_topics": [],
        "topic_clusters": [],
    }


# ── Link Analysis & Network Topology Endpoints ────────────────
class NetworkAnalyzeRequest(BaseModel):
    tweets: List[dict] = Field(..., description="List of tweets with user info, mentions, replies")
    edges: Optional[List[dict]] = Field(default=[], description="List of interaction edges")


@app.post("/api/network/analyze", tags=["Network Topology"])
async def analyze_network(req: NetworkAnalyzeRequest):
    """
    Constructs interaction graph, calculates centrality (PageRank, In/Out degree, Betweenness),
    identifies KOLs, clusters communities, and tracks spread cascades.
    """
    try:
        from analytics.network import get_network_engine
        engine = get_network_engine()
        result = engine.build_and_analyze(req.tweets, req.edges)
        return {
            "status": "success",
            "total_nodes": result.total_nodes,
            "total_edges": result.total_edges,
            "graph_density": result.graph_density,
            "nodes": result.nodes,
            "links": result.links,
            "influencers": [asdict(inf) for inf in result.influencers],
            "communities": [asdict(c) for c in result.communities],
            "spread_cascade": [asdict(s) for s in result.spread_cascade],
        }
    except Exception as ex:
        logger.error("network_analyze_error", error=str(ex))
        raise HTTPException(status_code=500, detail=f"Network analysis error: {str(ex)}")


@app.get("/network/influencers", tags=["Network Topology"])
async def get_top_influencers():
    """
    Returns Key Opinion Leaders (KOLs) identified from the latest session graph.
    """
    global _latest_network_summary
    if _latest_network_summary and "influencers" in _latest_network_summary:
        return {
            "status": "success",
            "influencers": _latest_network_summary["influencers"],
        }
    return {
        "status": "empty",
        "message": "No network graph computed yet. Run a search query in the Studio to map the network.",
        "influencers": [],
    }


@app.get("/network/communities", tags=["Network Topology"])
async def get_network_communities():
    """
    Returns user segment communities and sentiment flow from the latest session graph.
    """
    global _latest_network_summary
    if _latest_network_summary and "communities" in _latest_network_summary:
        return {
            "status": "success",
            "communities": _latest_network_summary["communities"],
            "spread_cascade": _latest_network_summary.get("spread_cascade", []),
        }
    return {
        "status": "empty",
        "message": "No community data computed yet.",
        "communities": [],
    }
