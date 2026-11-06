from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

from autohtmlvideo.config import AppConfig
from autohtmlvideo.models import ApprovedStory, StoryCandidate
from autohtmlvideo.storage import normalize_whitespace


def translate_to_zh(text: str) -> str:
    cleaned = normalize_whitespace(text)
    if not cleaned:
        return ""
    try:
        return normalize_whitespace(GoogleTranslator(source="en", target="zh-CN").translate(cleaned))
    except Exception:
        return cleaned


def trim_cn(text: str, limit: int) -> str:
    value = normalize_whitespace(text)
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip("，。；：,. ") + "。"


def sanitize_cn_summary(text: str) -> str:
    cleaned = normalize_whitespace(text)
    cleaned = re.sub(r"\s+[A-Za-z][A-Za-z0-9 .,'’:-]{5,}[。.]?$", "", cleaned).strip()
    return cleaned


def first_sentence(text: str) -> str:
    cleaned = normalize_whitespace(text)
    match = re.search(r"^(.+?[。！？!?])", cleaned)
    return match.group(1) if match else cleaned


def extract_page_summary(url: str) -> str:
    try:
        response = httpx.get(url, follow_redirects=True, timeout=25, headers={"user-agent": "Mozilla/5.0"})
        response.raise_for_status()
    except Exception:
        return ""
    soup = BeautifulSoup(response.text, "lxml")
    for selector in (
        'meta[property="og:description"]',
        'meta[name="description"]',
    ):
        node = soup.select_one(selector)
        if node and node.get("content"):
            return normalize_whitespace(node["content"])
    paragraph = soup.select_one("article p, main p, p")
    return normalize_whitespace(paragraph.get_text(" ", strip=True)) if paragraph else ""


def classify_topic(candidate: StoryCandidate) -> str:
    text = " ".join([candidate.merged_topic, *(item.summary for item in candidate.items)]).lower()
    if any(keyword in text for keyword in ("opus", "gpt", "gemini", "model", "claude", "release", "launch")):
        return "模型发布"
    if any(keyword in text for keyword in ("compute", "tpu", "gpu", "cloud", "data center", "gigawatts")):
        return "算力基础设施"
    if any(keyword in text for keyword in ("copilot", "product", "workspace", "app", "design")):
        return "产品更新"
    if any(keyword in text for keyword in ("policy", "safety", "trust", "government", "election")):
        return "治理与安全"
    return "行业动态"


def domain_label(url: str) -> str:
    host = urlparse(url).netloc.lower()
    host = host.replace("www.", "")
    return host


def build_script_sections(candidate: StoryCandidate, config: AppConfig) -> list[str]:
    primary = candidate.items[0]
    topic = classify_topic(candidate)
    zh_title = trim_cn(translate_to_zh(primary.title), 28)
    raw_summary = primary.summary or extract_page_summary(primary.url) or candidate.why_hot
    zh_summary = trim_cn(first_sentence(sanitize_cn_summary(translate_to_zh(raw_summary))), 42)
    supportive_sources = "、".join(dict.fromkeys(item.source for item in candidate.items[:3]))
    hook = trim_cn(f"今天的 AI 热点，核心是一句：{zh_title}", 34)
    happened = trim_cn(f"先看发生了什么：{zh_summary or zh_title}", 38)
    point_a = trim_cn(f"第一点，这是一个{topic}信号，不只是普通更新。", 28)
    if any(item.source == "Hacker News" for item in candidate.items):
        point_b = "第二点，这条消息已经带起社区讨论，热度正在往上走。"
    else:
        point_b = f"第二点，来源集中在 {supportive_sources}，可信度相对更稳。"
    impact = {
        "模型发布": "它会继续推高能力和迭代速度。",
        "算力基础设施": "它会影响训练和推理成本。",
        "产品更新": "它说明 AI 正在继续产品化。",
        "治理与安全": "它会影响企业采用和监管节奏。",
    }.get(topic, "它反映了 AI 产业仍在持续加速。")
    detail_b = f"{point_b}{impact}"
    if len(detail_b) > 40:
        detail_b = point_b
    if len(detail_b) > 40:
        detail_b = trim_cn(detail_b, 40)
    citation = trim_cn(
        f"消息来源包括 {supportive_sources}，原文链接已保留，方便你继续核查。",
        40,
    )
    sections = [hook, happened, point_a, detail_b, citation]
    total_chars = sum(len(section) for section in sections)
    if total_chars < 85:
        sections[3] = trim_cn(sections[3] + " 对开发者、产品团队和投资判断都有参考价值。", 42)
    if total_chars > 150:
        sections[1] = trim_cn(sections[1], 28)
        sections[3] = trim_cn(sections[3], 32)
    return sections


def build_scene_payload(candidate: StoryCandidate, sections: list[str]) -> dict:
    primary = candidate.items[0]
    zh_title = trim_cn(translate_to_zh(primary.title), 34)
    citations = [
        {
            "source": item.source,
            "url": item.url,
            "label": domain_label(item.url),
        }
        for item in candidate.items[:4]
    ]
    return {
        "brand": "AI Signal",
        "tag": classify_topic(candidate),
        "headline": zh_title,
        "deck": sections[0],
        "summary": sections[1],
        "detail_a": sections[2],
        "detail_b": sections[3],
        "source_text": sections[4],
        "citations": citations,
        "primary_url": primary.url,
        "primary_domain": domain_label(primary.url),
        "rank_score": f"{candidate.rank_score:.2f}",
    }


def build_story_title(candidate: StoryCandidate) -> str:
    base = trim_cn(translate_to_zh(candidate.items[0].title), 26)
    return trim_cn(f"AI快讯 | {base}", 32)


def build_story_description(candidate: StoryCandidate, sections: list[str]) -> str:
    source_lines = "\n".join(f"- {item.source}: {item.url}" for item in candidate.items[:4])
    hashtags = "#AI #科技资讯 #短视频 #自动化"
    return f"{sections[0]}\n{sections[1]}\n\n来源：\n{source_lines}\n\n{hashtags}"


def build_approved_story(candidate: StoryCandidate, config: AppConfig) -> ApprovedStory:
    sections = build_script_sections(candidate, config)
    scene_payload = build_scene_payload(candidate, sections)
    citation_list = [{"source": item.source, "url": item.url} for item in candidate.items]
    return ApprovedStory(
        candidate_id=candidate.id,
        cn_script="\n".join(sections),
        scene_payload=scene_payload,
        title=build_story_title(candidate),
        description=build_story_description(candidate, sections),
        citation_list=citation_list,
    )
