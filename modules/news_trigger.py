"""News-triggered AI scanning: replace fixed-timer AI with RSS keyword matching.

Instead of running expensive AI debate scans every N polling cycles regardless
of whether anything changed, this module monitors RSS feeds for breaking news
and only triggers AI analysis when relevant keywords appear.

Expected API cost reduction: 80-90% vs fixed-timer approach.

Usage:
    trigger = NewsTrigger(category_rules=CFG["category_rules"])
    trigger.start()  # background thread polls RSS every 60s
    ...
    # In scan loop:
    triggered = trigger.get_triggered_categories()
    if triggered:
        # Run AI only on these categories
        ...
"""
import time
import threading
import logging
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Optional

log = logging.getLogger("agent")


# Default RSS feeds covering major prediction market categories
DEFAULT_FEEDS = [
    ("reuters_top", "https://feeds.reuters.com/reuters/topNews"),
    ("reuters_business", "https://feeds.reuters.com/reuters/businessNews"),
    ("cnbc", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"),
    ("nyt_homepage", "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"),
    ("bbc_world", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("coindesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
]


class NewsItem:
    """A single news item from an RSS feed."""
    __slots__ = ("title", "description", "published", "source", "link", "seen_at")

    def __init__(self, title="", description="", published="", source="", link=""):
        self.title = title
        self.description = description
        self.published = published
        self.source = source
        self.link = link
        self.seen_at = time.time()


class NewsTrigger:
    """Monitor RSS feeds and trigger AI scans when relevant keywords appear.

    Maintains a sliding window of recent news items and matches them against
    the category_rules keyword dictionary used by the trading agent.
    """

    def __init__(self, category_rules=None, feeds=None, poll_interval_seconds=60,
                 cooldown_seconds=300, max_items=200):
        """
        Args:
            category_rules: dict of {category: [keywords]} from CFG
            feeds: list of (name, url) tuples for RSS feeds
            poll_interval_seconds: how often to check feeds
            cooldown_seconds: minimum time between triggers for same category
            max_items: max news items to keep in memory
        """
        self._category_rules = category_rules or {}
        self._feeds = feeds or DEFAULT_FEEDS
        self._poll_interval = poll_interval_seconds
        self._cooldown = cooldown_seconds
        self._max_items = max_items

        self._items = []  # list of NewsItem
        self._seen_titles = set()  # dedup
        self._triggered = {}  # category -> list of triggering NewsItems
        self._last_trigger_time = {}  # category -> timestamp
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_poll = 0
        self._stats = {"polls": 0, "items_fetched": 0, "triggers": 0, "errors": 0}

    def start(self):
        """Start background polling thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="news-trigger")
        self._thread.start()
        log.info(f"NewsTrigger: started ({len(self._feeds)} feeds, poll every {self._poll_interval}s)")

    def stop(self):
        """Stop the polling thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        log.info("NewsTrigger: stopped")

    def _poll_loop(self):
        """Background loop that polls RSS feeds."""
        while not self._stop_event.is_set():
            try:
                self._poll_all_feeds()
            except Exception as e:
                log.debug(f"NewsTrigger poll error: {e}")
                self._stats["errors"] += 1
            self._stop_event.wait(self._poll_interval)

    def _poll_all_feeds(self):
        """Fetch all RSS feeds and process new items."""
        import requests

        self._stats["polls"] += 1
        new_items = []

        for name, url in self._feeds:
            try:
                resp = requests.get(url, timeout=10, headers={
                    "User-Agent": "KalshiBot/1.0 (news-trigger)"
                })
                resp.raise_for_status()
                items = self._parse_rss(resp.text, source=name)
                new_items.extend(items)
            except Exception as e:
                log.debug(f"NewsTrigger: feed {name} failed: {e}")
                continue

        # Deduplicate and add new items
        added = 0
        with self._lock:
            for item in new_items:
                title_key = item.title.lower().strip()
                if title_key and title_key not in self._seen_titles:
                    self._seen_titles.add(title_key)
                    self._items.append(item)
                    added += 1
                    # Check for keyword matches
                    self._check_triggers(item)

            # Trim old items
            if len(self._items) > self._max_items:
                removed = self._items[:len(self._items) - self._max_items]
                for r in removed:
                    self._seen_titles.discard(r.title.lower().strip())
                self._items = self._items[-self._max_items:]

        self._stats["items_fetched"] += added
        self._last_poll = time.time()
        if added:
            log.debug(f"NewsTrigger: {added} new items from {len(self._feeds)} feeds")

    def _parse_rss(self, xml_text, source=""):
        """Parse RSS XML into NewsItem objects."""
        items = []
        try:
            root = ET.fromstring(xml_text)
            # Standard RSS 2.0
            for item_el in root.findall(".//item"):
                title = (item_el.findtext("title") or "").strip()
                desc = (item_el.findtext("description") or "").strip()
                pub = (item_el.findtext("pubDate") or "").strip()
                link = (item_el.findtext("link") or "").strip()
                if title:
                    items.append(NewsItem(
                        title=title, description=desc,
                        published=pub, source=source, link=link))

            # Atom feeds
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall(".//atom:entry", ns):
                title = (entry.findtext("atom:title", namespaces=ns) or "").strip()
                summary = (entry.findtext("atom:summary", namespaces=ns) or "").strip()
                pub = (entry.findtext("atom:published", namespaces=ns) or
                       entry.findtext("atom:updated", namespaces=ns) or "").strip()
                link_el = entry.find("atom:link", ns)
                link = link_el.get("href", "") if link_el is not None else ""
                if title:
                    items.append(NewsItem(
                        title=title, description=summary,
                        published=pub, source=source, link=link))
        except ET.ParseError:
            pass
        return items

    def _check_triggers(self, item):
        """Check if a news item matches any category keywords."""
        text = f"{item.title} {item.description}".lower()
        now = time.time()

        for category, keywords in self._category_rules.items():
            # Check cooldown
            last = self._last_trigger_time.get(category, 0)
            if now - last < self._cooldown:
                continue

            # Match keywords
            matches = [kw for kw in keywords if kw.lower() in text]
            if matches:
                if category not in self._triggered:
                    self._triggered[category] = []
                self._triggered[category].append(item)
                self._last_trigger_time[category] = now
                self._stats["triggers"] += 1
                log.info(f"  NewsTrigger: '{item.title[:60]}' -> category={category} "
                         f"(matched: {', '.join(matches[:3])})")

    def get_triggered_categories(self):
        """Pop all triggered categories since last call.

        Returns:
            dict of {category: [NewsItem, ...]} for categories that had news triggers
        """
        with self._lock:
            triggered = dict(self._triggered)
            self._triggered.clear()
            return triggered

    def has_triggers(self):
        """Check if any categories have been triggered (non-destructive)."""
        with self._lock:
            return bool(self._triggered)

    def force_trigger(self, category):
        """Manually trigger a category (for testing or manual override)."""
        with self._lock:
            if category not in self._triggered:
                self._triggered[category] = []
            self._triggered[category].append(
                NewsItem(title="Manual trigger", source="manual"))
            self._stats["triggers"] += 1

    def summary(self):
        """Return stats for dashboard display."""
        with self._lock:
            return {
                "active": self._thread is not None and self._thread.is_alive(),
                "feeds": len(self._feeds),
                "items_in_memory": len(self._items),
                "pending_triggers": list(self._triggered.keys()),
                "stats": dict(self._stats),
                "last_poll": self._last_poll,
            }
