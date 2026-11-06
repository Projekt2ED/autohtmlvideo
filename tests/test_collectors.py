from __future__ import annotations

import unittest
from datetime import datetime, timezone

from autohtmlvideo.collectors import (
    build_feed_items,
    merge_and_rank_candidates,
    parse_anthropic_news_html,
    parse_microsoft_ai_html,
)
from autohtmlvideo.config import default_config
from autohtmlvideo.models import SourceItem


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Introducing a new reasoning model</title>
      <link>https://example.com/model</link>
      <pubDate>Thu, 24 Apr 2026 10:00:00 GMT</pubDate>
      <description><![CDATA[<p>Faster reasoning and coding performance.</p>]]></description>
    </item>
  </channel>
</rss>
"""

SAMPLE_ANTHROPIC = """
<html><body>
  <a href="/news/claude-opus-4-7">Product Apr 16, 2026 Introducing Claude Opus 4.7 Our latest Opus model brings stronger coding performance.</a>
  <a href="/news/anthropic-nec">Apr 24, 2026 Announcements Anthropic and NEC collaborate to build Japan’s largest AI engineering workforce</a>
</body></html>
"""

SAMPLE_MICROSOFT = """
<html><body>
  <article>
    <a href="https://news.microsoft.com/source/features/ai/building-ai-that-works-for-everyone-starts-with-language/">Building AI that works for everyone starts with language</a>
    <div>Apr 24, 2026</div>
    <p>Microsoft explains how language coverage shapes practical AI products.</p>
  </article>
</body></html>
"""


class CollectorParsingTests(unittest.TestCase):
    def test_build_feed_items(self) -> None:
        items = build_feed_items("OpenAI News", "official", SAMPLE_RSS)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Introducing a new reasoning model")
        self.assertEqual(items[0].source_type, "official")

    def test_parse_anthropic_news_html(self) -> None:
        items = parse_anthropic_news_html(SAMPLE_ANTHROPIC)
        self.assertGreaterEqual(len(items), 2)
        self.assertTrue(any("Claude Opus" in item.title for item in items))

    def test_parse_microsoft_ai_html(self) -> None:
        items = parse_microsoft_ai_html(SAMPLE_MICROSOFT)
        self.assertEqual(len(items), 1)
        self.assertIn("Building AI", items[0].title)

    def test_merge_and_rank_candidates_dedupes_similar_titles(self) -> None:
        config = default_config()
        now = datetime.now(timezone.utc)
        items = [
            SourceItem(
                source="OpenAI News",
                source_type="official",
                title="Introducing GPT-5.5",
                url="https://openai.com/index/introducing-gpt-5-5",
                published_at=now,
                summary="A smarter model.",
            ),
            SourceItem(
                source="Hacker News",
                source_type="community",
                title="Introducing GPT 5.5",
                url="https://openai.com/index/introducing-gpt-5-5",
                published_at=now,
                summary="HN score 100.",
                score_raw=100,
            ),
        ]
        candidates = merge_and_rank_candidates(items, config)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(len(candidates[0].items), 2)


if __name__ == "__main__":
    unittest.main()

