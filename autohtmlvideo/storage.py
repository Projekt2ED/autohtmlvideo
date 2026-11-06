from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autohtmlvideo.models import ApprovedStory, CandidatesBundle, StoryCandidate


@dataclass(slots=True)
class ProjectPaths:
    root: Path
    workspace: Path
    raw_dir: Path
    candidates_dir: Path
    approved_dir: Path
    builds_dir: Path
    review_dir: Path
    temp_dir: Path

    @classmethod
    def from_root(cls, root: Path) -> "ProjectPaths":
        workspace = root / "workspace"
        paths = cls(
            root=root,
            workspace=workspace,
            raw_dir=workspace / "raw",
            candidates_dir=workspace / "candidates",
            approved_dir=workspace / "approved",
            builds_dir=workspace / "builds",
            review_dir=workspace / "review",
            temp_dir=workspace / "temp",
        )
        for path in (
            paths.workspace,
            paths.raw_dir,
            paths.candidates_dir,
            paths.approved_dir,
            paths.builds_dir,
            paths.review_dir,
            paths.temp_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        return paths

    @property
    def latest_candidates_path(self) -> Path:
        return self.candidates_dir / "latest.json"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp_slug(ts: datetime | None = None) -> str:
    value = ts or utc_now()
    return value.strftime("%Y%m%d-%H%M%S")


def slugify(text: str, limit: int = 48) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", text.lower()).strip("-")
    normalized = re.sub(r"-{2,}", "-", normalized)
    return normalized[:limit].strip("-") or "story"


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_candidates_bundle(paths: ProjectPaths, bundle: CandidatesBundle) -> Path:
    ts = timestamp_slug(bundle.generated_at)
    payload = bundle.model_dump(mode="json")
    archive_path = paths.candidates_dir / f"candidates-{ts}.json"
    raw_path = paths.raw_dir / f"source-items-{ts}.json"
    write_json(archive_path, payload)
    write_json(raw_path, {"generated_at": payload["generated_at"], "source_items": payload["source_items"], "errors": payload["errors"]})
    write_json(paths.latest_candidates_path, payload)
    return archive_path


def load_latest_candidates(paths: ProjectPaths) -> CandidatesBundle:
    return CandidatesBundle.model_validate(read_json(paths.latest_candidates_path))


def save_approved_story(paths: ProjectPaths, story: ApprovedStory) -> Path:
    path = paths.approved_dir / f"{story.candidate_id}.json"
    write_json(path, story.model_dump(mode="json"))
    return path


def load_approved_story(paths: ProjectPaths, story_id: str) -> ApprovedStory | None:
    path = paths.approved_dir / f"{story_id}.json"
    if not path.exists():
        return None
    return ApprovedStory.model_validate(read_json(path))


def save_review_selection(paths: ProjectPaths, candidate: StoryCandidate) -> Path:
    payload = {
        "candidate_id": candidate.id,
        "selected_at": utc_now().isoformat(),
        "candidate": candidate.model_dump(mode="json"),
    }
    path = paths.approved_dir / f"{candidate.id}.selected.json"
    write_json(path, payload)
    return path

