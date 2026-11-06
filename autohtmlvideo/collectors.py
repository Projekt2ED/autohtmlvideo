from __future__ import annotations

import difflib
import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Iterable
from urllib.parse import urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from autohtmlvideo.config import AppConfig
from autohtmlvideo.models import CandidatesBundle, SourceItem, StoryCandidate
from autohtmlvideo.storage import normalize_whitespace, slugify, utc_now


DEFAULT_HEADERS = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) autohtmlvideo/0.1",
}


def collect_candidates(config: AppConfig) -> CandidatesBundle:
    errors: list[dict[str, str]] = []
    items: list[SourceItem] = []
    for name, collector in (
        ("openai_news", collect_openai_news),
        ("anthropic_news", collect_anthropic_news),
        ("google_ai_blog", collect_google_ai_blog),
        ("microsoft_ai_blog", collect_microsoft_ai_blog),
        ("hn_topstories", collect_hacker_news),
    ):
        try:
            items.extend(collector(config))
        except Exception as exc:
            errors.append({"source": name, "error": str(exc)})
    recent_items = filter_recent_items(items, hours=config.recent_hours)
    candidates = merge_and_rank_candidates(recent_items, config)[: config.candidate_limit]
    return CandidatesBundle(source_items=recent_items, candidates=candidates, errors=errors)


def filter_recent_items(items: Iterable[SourceItem], hours: int) -> list[SourceItem]:
    cutoff = utc_now() - timedelta(hours=hours)
    return sorted([item for item in items if item.published_at >= cutoff], key=lambda item: item.published_at, reverse=True)


def fetch_text(url: str) -> str:
    response = httpx.get(url, headers=DEFAULT_HEADERS, follow_redirects=True, timeout=30)
    response.raise_for_status()
    return response.text


def parse_rfc822(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def clean_summary(value: str) -> str:
    soup = BeautifulSoup(value or "", "lxml")
    text = normalize_whitespace(unescape(soup.get_text(" ", strip=True)))
    return text


def build_feed_items(source: str, source_type: str, xml_text: str) -> list[SourceItem]:
    feed = feedparser.parse(xml_text)
    output: list[SourceItem] = []
    for entry in feed.entries:
        published = parse_rfc822(getattr(entry, "published", None)) or utc_now()
        title = normalize_whitespace(getattr(entry, "title", ""))
        link = getattr(entry, "link", "")
        summary = clean_summary(getattr(entry, "summary", "")) or clean_summary(getattr(entry, "description", ""))
        if not title or not link:
            continue
        output.append(
            SourceItem(
                source=source,
                source_type=source_type,
                title=title,
                url=link,
                published_at=published,
                summary=summary,
                score_raw=0.0,
                evidence_urls=[link],
            )
        )
    return output


def collect_openai_news(config: AppConfig) -> list[SourceItem]:
    text = fetch_text(config.source_urls["openai_news"])
    return build_feed_items("OpenAI News", "official", text)


def collect_google_ai_blog(config: AppConfig) -> list[SourceItem]:
    text = fetch_text(config.source_urls["google_ai_blog"])
    return build_feed_items("Google AI Blog", "official", text)


MONTH_RE = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+\d{4}"


def parse_anthropic_news_html(html: str) -> list[SourceItem]:
    soup = BeautifulSoup(html, "lxml")
    results: list[SourceItem] = []
    seen: set[str] = set()
    for anchor in soup.select('a[href^="/news/"]'):
        href = anchor.get("href", "")
        title_text = normalize_whitespace(anchor.get_text(" ", strip=True))
        if not href or not title_text:
            continue
        url = f"https://www.anthropic.com{href}".rstrip("/")
        if url in seen:
            continue
        seen.add(url)
        match = re.search(MONTH_RE, title_text)
        published = utc_now()
        if match:
            published = datetime.strptime(match.group(0), "%b %d, %Y").replace(tzinfo=timezone.utc)
        parts = [part.strip() for part in re.split(MONTH_RE, title_text) if part.strip()]
        summary = ""
        title = title_text
        if len(parts) >= 2:
            title = parts[-1]
        title = re.sub(r"^(Product|Announcements|Research)\s+", "", title).strip()
        if len(title.split()) < 3:
            continue
        results.append(
            SourceItem(
                source="Anthropic News",
                source_type="official",
                title=title,
                url=url,
                published_at=published,
                summary=summary,
                score_raw=0.0,
                evidence_urls=[url],
            )
        )
    return results


def collect_anthropic_news(config: AppConfig) -> list[SourceItem]:
    html = fetch_text(config.source_urls["anthropic_news"])
    return parse_anthropic_news_html(html)


def render_microsoft_page(url: str) -> str:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1800})
        page.goto(url, wait_until="networkidle", timeout=90000)
        html = page.content()
        browser.close()
    return html


def parse_microsoft_ai_html(html: str) -> list[SourceItem]:
    soup = BeautifulSoup(html, "lxml")
    results: list[SourceItem] = []
    seen: set[str] = set()
    for article in soup.select("article"):
        title_link = None
        for anchor in article.select("a[href]"):
            href = anchor.get("href", "")
            if "/source/" in href and "tag/" not in href:
                title_link = anchor
                break
        if title_link is None:
            continue
        url = title_link.get("href", "").rstrip("/")
        if not url or url in seen:
            continue
        seen.add(url)
        title = normalize_whitespace(title_link.get_text(" ", strip=True))
        if not title:
            continue
        text = normalize_whitespace(article.get_text(" ", strip=True))
        published = utc_now()
        date_match = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},\s+\d{4}", text)
        if date_match:
            published = datetime.strptime(date_match.group(0).replace(".", ""), "%b %d, %Y").replace(tzinfo=timezone.utc)
        summary = text.replace(title, "", 1).strip()
        results.append(
            SourceItem(
                source="Microsoft AI Blog",
                source_type="official",
                title=title,
                url=url,
                published_at=published,
                summary=summary,
                score_raw=0.0,
                evidence_urls=[url],
            )
        )
    return results


def collect_microsoft_ai_blog(config: AppConfig) -> list[SourceItem]:
    html = render_microsoft_page(config.source_urls["microsoft_ai_blog"])
    return parse_microsoft_ai_html(html)


def is_ai_related(text: str, config: AppConfig) -> bool:
    lowered = (text or "").lower()
    return any(keyword in lowered for keyword in config.ai_keywords)


def credible_hn_domain(url: str, config: AppConfig) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == domain or host.endswith(f".{domain}") for domain in config.trusted_hn_domains)


def collect_hacker_news(config: AppConfig) -> list[SourceItem]:
    ids = httpx.get(config.source_urls["hn_topstories"], headers=DEFAULT_HEADERS, timeout=30).json()
    results: list[SourceItem] = []
    for item_id in ids[: config.hn_fetch_limit]:
        item = httpx.get(
            f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json",
            headers=DEFAULT_HEADERS,
            timeout=30,
        ).json()
        if item.get("type") != "story":
            continue
        title = normalize_whitespace(item.get("title", ""))
        url = item.get("url")
        if not title or not url:
            continue
        if not is_ai_related(title + " " + url, config):
            continue
        if not credible_hn_domain(url, config):
            continue
        published = datetime.fromtimestamp(item["time"], tz=timezone.utc)
        score = float(item.get("score", 0.0))
        summary = f"Hacker News 讨论热度 {int(score)} 分。"
        results.append(
            SourceItem(
                source="Hacker News",
                source_type="community",
                title=title,
                url=url,
                published_at=published,
                summary=summary,
                score_raw=score,
                evidence_urls=[
                    f"https://news.ycombinator.com/item?id={item_id}",
                    url,
                ],
                metadata={"hn_id": item_id, "hn_score": score, "by": item.get("by", "")},
            )
        )
    return results


STOPWORDS = {
    "the",
    "a",
    "an",
    "for",
    "to",
    "and",
    "with",
    "of",
    "in",
    "on",
    "how",
    "is",
    "are",
    "by",
    "at",
    "from",
}


def normalize_title_tokens(title: str) -> list[str]:
    parts = re.findall(r"[a-zA-Z0-9]+", title.lower())
    return [part for part in parts if part not in STOPWORDS and len(part) > 1]


def similarity(left: str, right: str) -> float:
    left_tokens = normalize_title_tokens(left)
    right_tokens = normalize_title_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    left_set = set(left_tokens)
    right_set = set(right_tokens)
    jaccard = len(left_set & right_set) / len(left_set | right_set)
    ratio = difflib.SequenceMatcher(a=" ".join(left_tokens), b=" ".join(right_tokens)).ratio()
    return (jaccard * 0.6) + (ratio * 0.4)


def score_candidate(items: list[SourceItem], config: AppConfig) -> tuple[float, str]:
    now = utc_now()
    freshness = []
    official_bonus = 0.0
    community_heat = 0.0
    ai_relevance = 0.0
    duplicate_penalty = max(0, len(items) - 1) * 0.05
    sources = Counter(item.source for item in items)
    for item in items:
        age_hours = max(0.0, (now - item.published_at).total_seconds() / 3600)
        freshness.append(max(0.0, 1.0 - (age_hours / config.recent_hours)))
        official_bonus += 1.0 if item.source_type == "official" else 0.35
        community_heat += min(item.score_raw / 300.0, 1.0)
        ai_relevance += 1.0 if is_ai_related(f"{item.title} {item.summary}", config) else 0.3
    score = (sum(freshness) / max(len(freshness), 1)) * 0.35
    score += min(official_bonus / max(len(items), 1), 1.0) * 0.30
    score += min(community_heat, 1.0) * 0.20
    score += min(ai_relevance / max(len(items), 1), 1.0) * 0.20
    score -= duplicate_penalty
    source_text = "、".join(sorted(sources))
    why_hot = f"近 {config.recent_hours} 小时内命中 {source_text}，新鲜度和 AI 相关度较高。"
    return round(score, 4), why_hot


def merge_and_rank_candidates(items: list[SourceItem], config: AppConfig) -> list[StoryCandidate]:
    groups: list[list[SourceItem]] = []
    for item in sorted(items, key=lambda value: (value.published_at, value.score_raw), reverse=True):
        matched = False
        for group in groups:
            anchor = group[0]
            if similarity(item.title, anchor.title) >= 0.74:
                group.append(item)
                matched = True
                break
        if not matched:
            groups.append([item])
    candidates: list[StoryCandidate] = []
    for group in groups:
        score, why_hot = score_candidate(group, config)
        primary = sorted(group, key=lambda item: (item.source_type == "official", item.score_raw, item.published_at), reverse=True)[0]
        candidate_id = slugify(primary.title)
        candidates.append(
            StoryCandidate(
                id=candidate_id,
                merged_topic=primary.title,
                items=sorted(group, key=lambda item: (item.source_type == "official", item.score_raw, item.published_at), reverse=True),
                rank_score=score,
                why_hot=why_hot,
            )
        )
    candidates.sort(key=lambda candidate: candidate.rank_score, reverse=True)
    deduped: list[StoryCandidate] = []
    seen_ids: set[str] = set()
    for candidate in candidates:
        unique_id = candidate.id
        counter = 2
        while unique_id in seen_ids:
            unique_id = f"{candidate.id}-{counter}"
            counter += 1
        if unique_id != candidate.id:
            candidate = candidate.model_copy(update={"id": unique_id})
        seen_ids.add(unique_id)
        deduped.append(candidate)
    return deduped
