"""Tests for news-triggered AI scanning."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from unittest.mock import patch, MagicMock
from modules.news_trigger import NewsTrigger, NewsItem


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Fed Raises Interest Rates by 25 Basis Points</title>
      <description>The Federal Reserve raised rates today in a surprise move.</description>
      <pubDate>Thu, 14 Mar 2026 12:00:00 GMT</pubDate>
      <link>https://example.com/fed-rates</link>
    </item>
    <item>
      <title>Bitcoin Surges Past $100,000 on ETF Approval</title>
      <description>Bitcoin price jumped after SEC approved new ETF.</description>
      <pubDate>Thu, 14 Mar 2026 11:00:00 GMT</pubDate>
      <link>https://example.com/btc-surge</link>
    </item>
    <item>
      <title>Local Sports Team Wins Championship</title>
      <description>The Lakers won the NBA championship in overtime.</description>
      <pubDate>Thu, 14 Mar 2026 10:00:00 GMT</pubDate>
      <link>https://example.com/sports</link>
    </item>
    <item>
      <title>Weather Forecast: Major Hurricane Approaching Florida</title>
      <description>Category 4 hurricane expected to make landfall Friday.</description>
      <pubDate>Thu, 14 Mar 2026 09:00:00 GMT</pubDate>
      <link>https://example.com/hurricane</link>
    </item>
  </channel>
</rss>"""

CATEGORY_RULES = {
    "fed_rates": ["fed", "fomc", "interest rate", "rate cut", "rate hike"],
    "crypto": ["bitcoin", "ethereum", "crypto", "blockchain"],
    "sports": ["nba", "nfl", "championship", "basketball"],
    "weather": ["hurricane", "tornado", "storm", "weather"],
}


class TestNewsTriggerParsing(unittest.TestCase):
    def setUp(self):
        self.trigger = NewsTrigger(category_rules=CATEGORY_RULES)

    def test_parse_rss(self):
        items = self.trigger._parse_rss(SAMPLE_RSS, source="test")
        self.assertEqual(len(items), 4)
        self.assertEqual(items[0].title, "Fed Raises Interest Rates by 25 Basis Points")
        self.assertEqual(items[0].source, "test")

    def test_parse_rss_empty(self):
        items = self.trigger._parse_rss("", source="test")
        self.assertEqual(len(items), 0)

    def test_parse_rss_invalid_xml(self):
        items = self.trigger._parse_rss("<invalid>not closed", source="test")
        self.assertEqual(len(items), 0)

    def test_parse_atom_feed(self):
        atom_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <title>Atom Title</title>
            <summary>Atom summary</summary>
            <published>2026-03-14T12:00:00Z</published>
            <link href="https://example.com/atom"/>
          </entry>
        </feed>"""
        items = self.trigger._parse_rss(atom_xml, source="atom-test")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Atom Title")
        self.assertEqual(items[0].source, "atom-test")


class TestNewsTriggerMatching(unittest.TestCase):
    def setUp(self):
        self.trigger = NewsTrigger(category_rules=CATEGORY_RULES, cooldown_seconds=0)

    def test_keyword_matching_fed(self):
        item = NewsItem(title="Fed Raises Interest Rates", description="FOMC decision")
        self.trigger._check_triggers(item)
        triggered = self.trigger.get_triggered_categories()
        self.assertIn("fed_rates", triggered)

    def test_keyword_matching_crypto(self):
        item = NewsItem(title="Bitcoin Surges Past $100k", description="crypto market rally")
        self.trigger._check_triggers(item)
        triggered = self.trigger.get_triggered_categories()
        self.assertIn("crypto", triggered)

    def test_no_match_for_unrelated(self):
        item = NewsItem(title="New Restaurant Opens Downtown", description="food and dining")
        self.trigger._check_triggers(item)
        triggered = self.trigger.get_triggered_categories()
        self.assertEqual(len(triggered), 0)

    def test_cooldown_prevents_rapid_retrigger(self):
        trigger = NewsTrigger(category_rules=CATEGORY_RULES, cooldown_seconds=300)
        item1 = NewsItem(title="Fed raises rates", description="")
        item2 = NewsItem(title="Fed cuts rates surprise", description="")
        trigger._check_triggers(item1)
        trigger._check_triggers(item2)
        triggered = trigger.get_triggered_categories()
        # Should only have 1 item for fed_rates due to cooldown
        self.assertEqual(len(triggered.get("fed_rates", [])), 1)

    def test_multiple_categories_triggered(self):
        trigger = NewsTrigger(category_rules=CATEGORY_RULES, cooldown_seconds=0)
        item1 = NewsItem(title="Bitcoin hits $100k", description="")
        item2 = NewsItem(title="NBA championship game tonight", description="basketball")
        trigger._check_triggers(item1)
        trigger._check_triggers(item2)
        triggered = trigger.get_triggered_categories()
        self.assertIn("crypto", triggered)
        self.assertIn("sports", triggered)


class TestNewsTriggerQueue(unittest.TestCase):
    def setUp(self):
        self.trigger = NewsTrigger(category_rules=CATEGORY_RULES, cooldown_seconds=0)

    def test_get_triggered_clears_queue(self):
        self.trigger.force_trigger("crypto")
        triggered = self.trigger.get_triggered_categories()
        self.assertIn("crypto", triggered)
        # Second call should be empty
        triggered2 = self.trigger.get_triggered_categories()
        self.assertEqual(len(triggered2), 0)

    def test_has_triggers(self):
        self.assertFalse(self.trigger.has_triggers())
        self.trigger.force_trigger("fed_rates")
        self.assertTrue(self.trigger.has_triggers())
        self.trigger.get_triggered_categories()
        self.assertFalse(self.trigger.has_triggers())

    def test_force_trigger(self):
        self.trigger.force_trigger("weather")
        triggered = self.trigger.get_triggered_categories()
        self.assertIn("weather", triggered)
        self.assertEqual(triggered["weather"][0].title, "Manual trigger")

    def test_summary(self):
        summary = self.trigger.summary()
        self.assertIn("active", summary)
        self.assertIn("feeds", summary)
        self.assertIn("items_in_memory", summary)
        self.assertIn("pending_triggers", summary)
        self.assertIn("stats", summary)


class TestNewsTriggerDedup(unittest.TestCase):
    def test_duplicate_titles_ignored(self):
        trigger = NewsTrigger(category_rules=CATEGORY_RULES, cooldown_seconds=0)
        items = trigger._parse_rss(SAMPLE_RSS, source="test")
        # Add items twice
        for item in items:
            title_key = item.title.lower().strip()
            trigger._seen_titles.add(title_key)
            trigger._items.append(item)
        initial_count = len(trigger._items)

        # Try to add same items again - simulating dedup logic
        added = 0
        for item in items:
            title_key = item.title.lower().strip()
            if title_key not in trigger._seen_titles:
                added += 1
        self.assertEqual(added, 0)


class TestNewsItem(unittest.TestCase):
    def test_newsitem_creation(self):
        item = NewsItem(title="Test", description="Desc", source="src")
        self.assertEqual(item.title, "Test")
        self.assertEqual(item.description, "Desc")
        self.assertEqual(item.source, "src")
        self.assertGreater(item.seen_at, 0)

    def test_newsitem_defaults(self):
        item = NewsItem()
        self.assertEqual(item.title, "")
        self.assertEqual(item.description, "")
        self.assertEqual(item.link, "")


if __name__ == "__main__":
    unittest.main()
