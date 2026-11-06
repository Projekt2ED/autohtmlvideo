from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SourceItem(BaseModel):
    source: str
    source_type: Literal["official", "community"]
    title: str
    url: str
    published_at: datetime
    summary: str = ""
    score_raw: float = 0.0
    evidence_urls: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @computed_field
    @property
    def canonical_url(self) -> str:
        return self.url.rstrip("/")


class StoryCandidate(BaseModel):
    id: str
    merged_topic: str
    items: list[SourceItem]
    rank_score: float
    why_hot: str
    created_at: datetime = Field(default_factory=utc_now)

    @computed_field
    @property
    def primary_url(self) -> str:
        official = [item for item in self.items if item.source_type == "official"]
        ranked = official or self.items
        ranked = sorted(ranked, key=lambda item: (item.score_raw, item.published_at), reverse=True)
        return ranked[0].url


class ApprovedStory(BaseModel):
    candidate_id: str
    cn_script: str
    scene_payload: dict[str, Any]
    title: str
    description: str
    citation_list: list[dict[str, str]]
    created_at: datetime = Field(default_factory=utc_now)


class RenderJob(BaseModel):
    story_id: str
    aspect: str = "9:16"
    duration_target: str = "20-40s"
    voice_profile: str = "zh-CN-XiaoxiaoNeural"
    theme: str = "signal-amber"


class CandidatesBundle(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    source_items: list[SourceItem] = Field(default_factory=list)
    candidates: list[StoryCandidate] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)

