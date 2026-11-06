from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import imageio_ffmpeg


@dataclass(slots=True)
class AppConfig:
    project_root: Path
    review_host: str = "127.0.0.1"
    review_port: int = 8765
    recent_hours: int = 36
    candidate_limit: int = 5
    hn_fetch_limit: int = 60
    viewport_width: int = 1080
    viewport_height: int = 1920
    fps: int = 30
    aspect: str = "9:16"
    duration_target: str = "20-40s"
    theme: str = "signal-amber"
    default_voice: str = "zh-CN-XiaoxiaoNeural"
    ai_keywords: tuple[str, ...] = (
        "ai",
        "artificial intelligence",
        "model",
        "models",
        "llm",
        "gpt",
        "claude",
        "gemini",
        "copilot",
        "inference",
        "agent",
        "agents",
        "reasoning",
        "multimodal",
        "compute",
        "gpu",
        "tpu",
        "training",
        "alignment",
        "safety",
    )
    trusted_hn_domains: tuple[str, ...] = (
        "openai.com",
        "anthropic.com",
        "google.com",
        "blog.google",
        "microsoft.com",
        "blogs.microsoft.com",
        "news.microsoft.com",
        "techcrunch.com",
        "theverge.com",
        "wired.com",
        "semianalysis.com",
        "huggingface.co",
        "arxiv.org",
    )
    source_urls: dict[str, str] = field(
        default_factory=lambda: {
            "openai_news": "https://openai.com/news/rss.xml",
            "anthropic_news": "https://www.anthropic.com/news",
            "google_ai_blog": "https://blog.google/technology/ai/rss/",
            "microsoft_ai_blog": "https://news.microsoft.com/source/topics/ai/",
            "hn_topstories": "https://hacker-news.firebaseio.com/v0/topstories.json",
        }
    )

    @property
    def ffmpeg_path(self) -> str:
        return imageio_ffmpeg.get_ffmpeg_exe()


def default_config(project_root: Path | None = None) -> AppConfig:
    root = (project_root or Path.cwd()).resolve()
    return AppConfig(project_root=root)

