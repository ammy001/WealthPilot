"""
data/news_rss.py
────────────────
Free Indian-market news via public RSS feeds (no API key). Vendored/trimmed
from india-trade-cli `market/news.py` — RSS path only, NewsAPI/keyring stripped.

Used to build a rolling "market report" section of the WealthPilot RAG corpus.
Returns NewsItem dataclasses: {title, source, url, published, summary}.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

try:
    import feedparser
    _FEEDPARSER_AVAILABLE = True
except ImportError:
    _FEEDPARSER_AVAILABLE = False


@dataclass
class NewsItem:
    title: str
    source: str
    url: str
    published: str  # ISO datetime string
    summary: str = ""


RSS_FEEDS = {
    "ET Markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "ET Stocks": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    "MoneyControl": "https://www.moneycontrol.com/rss/latestnews.xml",
    "Business Standard": "https://www.business-standard.com/rss/markets-106.rss",
    "Hindu BL": "https://www.thehindubusinessline.com/markets/?service=rss",
    "LiveMint Markets": "https://www.livemint.com/rss/markets",
}


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()[:400]


def get_rss_feed(url: str, source: str = "RSS", n: int = 10) -> list[NewsItem]:
    """Parse an RSS feed, return latest n items. Empty list on any failure."""
    if not _FEEDPARSER_AVAILABLE:
        return []
    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:n]:
            published = entry.get("published", entry.get("updated", ""))
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()
            items.append(NewsItem(
                title=entry.get("title", "").strip(),
                source=source,
                url=entry.get("link", ""),
                published=published,
                summary=_strip_html(entry.get("summary", "")),
            ))
        return items
    except Exception:
        return []


def get_market_news(n: int = 30, feeds: int = 4) -> list[NewsItem]:
    """Merged, de-duplicated Indian market headlines from the top RSS feeds."""
    items: list[NewsItem] = []
    for source, url in list(RSS_FEEDS.items())[:feeds]:
        items.extend(get_rss_feed(url, source, n=15))

    seen: set[str] = set()
    unique: list[NewsItem] = []
    for item in items:
        key = item.title[:60].lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    unique.sort(key=lambda x: x.published, reverse=True)
    return unique[:n]
