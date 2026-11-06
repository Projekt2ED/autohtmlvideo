from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from autohtmlvideo.config import default_config
from autohtmlvideo.models import SourceItem, StoryCandidate
from autohtmlvideo.render import format_srt_timestamp, generate_subtitle_cues, write_srt
from autohtmlvideo.review import REVIEW_TEMPLATE
from autohtmlvideo.textgen import build_approved_story


class StoryAndRenderTests(unittest.TestCase):
    def build_candidate(self) -> StoryCandidate:
        now = datetime.now(timezone.utc)
        item = SourceItem(
            source="OpenAI News",
            source_type="official",
            title="Introducing GPT-5.5",
            url="https://openai.com/index/introducing-gpt-5-5",
            published_at=now,
            summary="Introducing GPT-5.5, a more capable model for coding, research and data analysis.",
        )
        return StoryCandidate(
            id="introducing-gpt-5-5",
            merged_topic=item.title,
            items=[item],
            rank_score=0.91,
            why_hot="近 36 小时内命中官方发布。",
        )

    def test_build_approved_story_has_five_sections(self) -> None:
        story = build_approved_story(self.build_candidate(), default_config())
        sections = [line for line in story.cn_script.splitlines() if line.strip()]
        self.assertEqual(len(sections), 5)
        self.assertIn("来源", sections[-1])
        self.assertLess(sum(len(line) for line in sections), 170)

    def test_generate_subtitle_cues_cover_full_duration(self) -> None:
        script = "第一句。\n第二句。\n第三句。"
        cues = generate_subtitle_cues(script, 24.0)
        self.assertEqual(len(cues), 3)
        self.assertAlmostEqual(cues[0].start, 0.0)
        self.assertAlmostEqual(cues[-1].end, 24.0)

    def test_write_srt(self) -> None:
        cues = generate_subtitle_cues("第一句。\n第二句。", 12.0)
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "subtitles.srt"
            write_srt(cues, output)
            content = output.read_text(encoding="utf-8")
            self.assertIn("00:00:00,000", content)
            self.assertIn("第一句。", content)

    def test_format_srt_timestamp(self) -> None:
        self.assertEqual(format_srt_timestamp(12.345), "00:00:12,345")

    def test_review_template_renders_candidate_dict(self) -> None:
        candidate = self.build_candidate().model_dump(mode="json")
        html = REVIEW_TEMPLATE.render(candidates=[candidate])
        self.assertIn(candidate["id"], html)
        self.assertIn(candidate["items"][0]["title"], html)


if __name__ == "__main__":
    unittest.main()
