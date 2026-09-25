"""
Real-Time Trend & Topic Detection Engine.

Features:
- Chronological tokenization & entity extraction (hashtags, keywords, n-grams).
- Dynamic time-window burst detection & velocity calculation:
    velocity = (freq_current - freq_baseline) / max(1, freq_baseline)
- Virality & Momentum prediction:
    combines velocity, acceleration, volume, and engagement multipliers.
- Topic Clustering: co-occurrence graph clustering grouping related terms into topics.
- Chronological Discussion Shifts: tracking how topics evolve from early to late phases.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from logging_config import get_logger

logger = get_logger("analytics.trends")

# Multilingual Stopwords (English + Hinglish + Common Indic markers)
_STOPWORDS: Set[str] = {
    # English
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "did", "do", "does", "doing", "don't", "down", "during", "each", "few", "for",
    "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers",
    "him", "his", "how", "i", "if", "in", "into", "is", "isn't", "it", "its",
    "itself", "just", "me", "more", "most", "my", "myself", "no", "nor", "not",
    "now", "of", "off", "on", "once", "only", "or", "other", "ought", "our",
    "ours", "ourselves", "out", "over", "own", "same", "she", "should", "so",
    "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves",
    "then", "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "we", "were", "what", "when", "where",
    "which", "while", "who", "whom", "why", "with", "would", "you", "your", "yours",
    "yourself", "yourselves", "http", "https", "t", "co", "rt", "amp", "via", "will",
    # Hinglish & Hindi fillers
    "hai", "hain", "ko", "ki", "ka", "ke", "me", "mein", "se", "aur", "bhi", "ye",
    "yeh", "wo", "woh", "kar", "kare", "karna", "ho", "raha", "rahe", "rahi", "tha",
    "the", "thi", "par", "ek", "kuch", "apne", "ab", "iss", "issk", "kya", "kyu",
    "kyun", "toh", "to", "bjp", "aap", "congress", "delhi", "modi", "sir", "bhai",
}

_URL_PATTERN = re.compile(r"https?://\S+|www\.\S+")
_PUNCT_PATTERN = re.compile(r"[^\w\s#@]")


@dataclass
class TrendItem:
    keyword_or_topic: str
    is_hashtag: bool
    total_volume: int
    recent_volume: int
    baseline_volume: int
    growth_rate: float  # Velocity: percentage surge over baseline
    acceleration: float  # Rate of velocity change
    virality_score: float  # Composite 0.0 - 100.0
    virality_status: str  # "Explosive Growth" | "Rising" | "Steady Trend" | "Fading"
    engagement_reach: int
    representative_posts: List[int] = field(default_factory=list)


@dataclass
class TopicCluster:
    topic_id: int
    topic_label: str
    top_terms: List[str]
    volume: int
    growth_rate: float
    sentiment_distribution: Dict[str, float]
    sample_snippets: List[str]


@dataclass
class TrendAnalysisResult:
    total_posts: int
    analyzed_window_hours: float
    rising_trends: List[TrendItem]
    predicted_viral_topics: List[TrendItem]
    topic_clusters: List[TopicCluster]
    chronological_shifts: List[Dict[str, Any]]


class TrendEngine:
    """
    Analyzes temporal tweet streams to extract rising trends, topic clusters,
    and predict emergent virality.
    """

    def __init__(self):
        logger.info("trend_engine_initialized")

    def _clean_and_tokenize(self, text: str) -> Tuple[List[str], List[str]]:
        """
        Extracts clean keywords and hashtags from tweet text.
        Returns (keywords, hashtags).
        """
        # Strip URLs
        cleaned = _URL_PATTERN.sub("", text)
        
        # Extract hashtags
        hashtags = [h.strip("#").lower() for h in re.findall(r"#\w+", cleaned)]
        hashtags = [h for h in hashtags if len(h) >= 2]

        # Tokenize words
        words = _PUNCT_PATTERN.sub(" ", cleaned).lower().split()
        keywords = [
            w for w in words
            if len(w) >= 3
            and w not in _STOPWORDS
            and not w.startswith("@")
            and not w.isdigit()
        ]

        return keywords, hashtags

    def analyze_stream(
        self,
        tweets: List[Dict[str, Any]],
        num_windows: int = 3,
    ) -> TrendAnalysisResult:
        """
        Performs full trend detection on a chronological list of tweets.
        
        Each tweet dict is expected to have:
          - post_id: int or str
          - text: str
          - created_at: datetime or ISO string (optional)
          - like_count: int (optional)
          - retweet_count: int (optional)
          - sentiment: dict (optional, e.g. {"label": "positive"})
        """
        if not tweets:
            return TrendAnalysisResult(
                total_posts=0,
                analyzed_window_hours=0.0,
                rising_trends=[],
                predicted_viral_topics=[],
                topic_clusters=[],
                chronological_shifts=[],
            )

        total_posts = len(tweets)

        # Sort chronologically if timestamps available
        def parse_dt(item: Dict[str, Any]) -> datetime:
            val = item.get("created_at")
            if isinstance(val, datetime):
                return val
            if isinstance(val, str):
                try:
                    return datetime.fromisoformat(val.replace("Z", "+00:00"))
                except Exception:
                    pass
            return datetime.min

        sorted_tweets = sorted(tweets, key=parse_dt)
        has_dates = any(parse_dt(t) != datetime.min for t in sorted_tweets)
        
        if has_dates and len(sorted_tweets) >= 2:
            first_dt = parse_dt(sorted_tweets[0])
            last_dt = parse_dt(sorted_tweets[-1])
            if first_dt != datetime.min and last_dt != datetime.min:
                window_hours = max(0.1, (last_dt - first_dt).total_seconds() / 3600.0)
            else:
                window_hours = 1.0
        else:
            window_hours = 1.0

        # Partition tweets into chronological windows (Early, Mid, Late)
        # Even if timestamps are missing/uniform, position in the stream reflects chronological order
        k = max(2, min(num_windows, total_posts))
        chunk_size = math.ceil(total_posts / k)
        windows = [sorted_tweets[i * chunk_size : (i + 1) * chunk_size] for i in range(k)]

        # Global counters & Per-window counters
        global_term_counts: Counter[str] = Counter()
        global_hashtag_counts: Counter[str] = Counter()
        term_engagement: Dict[str, int] = defaultdict(int)
        term_posts: Dict[str, List[int]] = defaultdict(list)
        co_occurrence: Dict[str, Counter[str]] = defaultdict(Counter)

        window_term_counts: List[Counter[str]] = [Counter() for _ in range(k)]

        # Process each window
        for w_idx, win in enumerate(windows):
            for t in win:
                pid = t.get("post_id") or 0
                text = t.get("text", "")
                eng = (t.get("like_count") or 0) + (t.get("retweet_count") or 0) * 2

                keywords, hashtags = self._clean_and_tokenize(text)

                # Combine hashtags & keywords
                all_terms = []
                for h in hashtags:
                    tag = f"#{h}"
                    all_terms.append(tag)
                    global_hashtag_counts[tag] += 1
                for kw in keywords:
                    all_terms.append(kw)

                unique_terms = list(set(all_terms))
                for term in unique_terms:
                    global_term_counts[term] += 1
                    window_term_counts[w_idx][term] += 1
                    term_engagement[term] += eng
                    term_posts[term].append(pid)

                # Build co-occurrence for topic clustering
                for i in range(len(unique_terms)):
                    for j in range(i + 1, min(i + 6, len(unique_terms))):
                        t1, t2 = unique_terms[i], unique_terms[j]
                        co_occurrence[t1][t2] += 1
                        co_occurrence[t2][t1] += 1

        # Calculate Growth Rate (Velocity) & Acceleration
        # Baseline = average of earlier windows, Recent = last window
        trend_items: List[TrendItem] = []
        recent_window = window_term_counts[-1]
        baseline_windows = window_term_counts[:-1]
        num_baseline = len(baseline_windows)

        for term, total_vol in global_term_counts.items():
            if total_vol < 2 and total_posts >= 5:
                continue

            recent_vol = recent_window[term]
            baseline_avg = (
                sum(bw[term] for bw in baseline_windows) / num_baseline
                if num_baseline > 0
                else total_vol / 2.0
            )

            # Growth rate (velocity) = percentage surge over baseline
            if baseline_avg > 0:
                growth_rate = ((recent_vol - baseline_avg) / baseline_avg) * 100.0
            else:
                growth_rate = recent_vol * 150.0  # Brand new emerging burst

            # Acceleration = change across mid to late if >= 3 windows
            if len(window_term_counts) >= 3:
                mid_vol = window_term_counts[-2][term]
                prev_rate = ((mid_vol - window_term_counts[0][term]) / max(0.5, window_term_counts[0][term]))
                curr_rate = ((recent_vol - mid_vol) / max(0.5, mid_vol))
                acceleration = round((curr_rate - prev_rate), 2)
            else:
                acceleration = round(growth_rate / 100.0, 2)

            # Virality Score calculation (0 - 100)
            # Factors: Velocity (40%), Acceleration (20%), Volume (25%), Engagement reach (15%)
            norm_vol = min(1.0, total_vol / max(5, total_posts * 0.4))
            norm_vel = max(0.0, min(1.0, (growth_rate + 50) / 250.0))
            norm_acc = max(0.0, min(1.0, (acceleration + 1.0) / 3.0))
            norm_eng = min(1.0, term_engagement[term] / max(10, total_posts * 5))

            virality_score = round(
                (norm_vel * 40.0 + norm_acc * 20.0 + norm_vol * 25.0 + norm_eng * 15.0),
                1
            )

            # Virality status determination
            if virality_score >= 70.0 and growth_rate > 50.0:
                status = "Explosive Growth"
            elif virality_score >= 45.0 or growth_rate > 20.0:
                status = "Rising"
            elif growth_rate < -20.0:
                status = "Fading"
            else:
                status = "Steady Trend"

            trend_items.append(
                TrendItem(
                    keyword_or_topic=term,
                    is_hashtag=term.startswith("#"),
                    total_volume=total_vol,
                    recent_volume=recent_vol,
                    baseline_volume=round(baseline_avg, 1),
                    growth_rate=round(growth_rate, 1),
                    acceleration=acceleration,
                    virality_score=virality_score,
                    virality_status=status,
                    engagement_reach=term_engagement[term],
                    representative_posts=term_posts[term][:5],
                )
            )

        # Sort rising trends: primary by growth_rate desc, then virality_score
        rising_trends = sorted(trend_items, key=lambda x: (x.growth_rate, x.virality_score), reverse=True)

        # Predicted viral topics: sorted by virality_score desc
        predicted_viral = sorted(trend_items, key=lambda x: (x.virality_score, x.recent_volume), reverse=True)

        # Topic Clustering: group terms that frequently co-occur together
        clusters = self._cluster_topics(sorted_tweets, global_term_counts, co_occurrence)

        # Chronological Shifts: summarize top discussion terms in each window
        shifts = []
        phase_names = ["Early Phase", "Mid Phase", "Late / Current Phase"]
        for idx, win_counter in enumerate(window_term_counts):
            phase_label = phase_names[idx] if idx < len(phase_names) else f"Phase {idx + 1}"
            top_in_win = win_counter.most_common(5)
            shifts.append({
                "phase_index": idx,
                "phase_name": phase_label,
                "post_count": len(windows[idx]),
                "dominant_topics": [{"term": t, "count": c} for t, c in top_in_win],
            })

        return TrendAnalysisResult(
            total_posts=total_posts,
            analyzed_window_hours=round(window_hours, 2),
            rising_trends=rising_trends[:15],
            predicted_viral_topics=predicted_viral[:10],
            topic_clusters=clusters[:6],
            chronological_shifts=shifts,
        )

    def _cluster_topics(
        self,
        tweets: List[Dict[str, Any]],
        term_counts: Counter[str],
        co_occurrence: Dict[str, Counter[str]],
    ) -> List[TopicCluster]:
        """
        Clusters terms into coherent topics using co-occurrence graphs.
        """
        top_seed_terms = [t for t, _ in term_counts.most_common(20)]
        visited: Set[str] = set()
        clusters: List[TopicCluster] = []
        cluster_id = 1

        for seed in top_seed_terms:
            if seed in visited:
                continue

            # Find closely related co-occurring terms
            related = co_occurrence[seed].most_common(6)
            cluster_terms = [seed]
            visited.add(seed)

            for rel_term, score in related:
                if rel_term not in visited and score >= 1:
                    cluster_terms.append(rel_term)
                    visited.add(rel_term)
                if len(cluster_terms) >= 5:
                    break

            if len(cluster_terms) < 2 and len(top_seed_terms) > 5:
                continue

            # Calculate cluster aggregate metrics
            cluster_vol = sum(term_counts[t] for t in cluster_terms)
            
            # Label topic based on top terms
            primary_label = cluster_terms[0].upper().replace("#", "")
            secondary_label = cluster_terms[1].upper().replace("#", "") if len(cluster_terms) > 1 else ""
            topic_label = f"{primary_label} & {secondary_label}" if secondary_label else primary_label

            # Gather sample matching snippets & sentiment
            sample_snippets = []
            sentiments: Counter[str] = Counter()

            for t in tweets:
                text = t.get("text", "")
                text_lower = text.lower()
                if any(term.lower() in text_lower for term in cluster_terms):
                    if len(sample_snippets) < 3:
                        sample_snippets.append(text[:140] + ("..." if len(text) > 140 else ""))
                    sent = t.get("sentiment", {})
                    if isinstance(sent, dict) and "label" in sent:
                        sentiments[sent["label"]] += 1

            total_sent = sum(sentiments.values()) or 1
            sent_dist = {
                k: round(v / total_sent, 2)
                for k, v in sentiments.items()
            }

            clusters.append(
                TopicCluster(
                    topic_id=cluster_id,
                    topic_label=topic_label,
                    top_terms=cluster_terms,
                    volume=cluster_vol,
                    growth_rate=round(float(min(300.0, cluster_vol * 15.0)), 1),
                    sentiment_distribution=sent_dist,
                    sample_snippets=sample_snippets,
                )
            )
            cluster_id += 1

        return clusters


_engine_singleton: Optional[TrendEngine] = None

def get_trend_engine() -> TrendEngine:
    global _engine_singleton
    if _engine_singleton is None:
        _engine_singleton = TrendEngine()
    return _engine_singleton
