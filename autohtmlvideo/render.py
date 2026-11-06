from __future__ import annotations

import json
import math
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Template
from playwright.sync_api import sync_playwright

from autohtmlvideo.config import AppConfig
from autohtmlvideo.models import ApprovedStory, RenderJob, StoryCandidate
from autohtmlvideo.storage import ProjectPaths, save_approved_story, timestamp_slug, write_json
from autohtmlvideo.textgen import build_approved_story
from autohtmlvideo.tts import SynthesisResult, synthesize_voice


@dataclass(slots=True)
class SubtitleCue:
    index: int
    start: float
    end: float
    text: str


VIDEO_TEMPLATE = Template(
    """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }}</title>
  <style>
    :root {
      --bg0: #05070b;
      --bg1: #0f1420;
      --ink: #eef2ff;
      --muted: #9fb1cf;
      --line: rgba(255, 255, 255, 0.14);
      --accent: #ff8d3a;
      --accent2: #5da9ff;
      --panel: rgba(7, 12, 22, 0.78);
      --shadow: 0 36px 120px rgba(0, 0, 0, 0.38);
    }
    * { box-sizing: border-box; }
    html, body {
      width: 100%;
      height: 100%;
      margin: 0;
      overflow: hidden;
      background: radial-gradient(circle at 15% 20%, rgba(255,141,58,0.14), transparent 28%),
                  radial-gradient(circle at 85% 15%, rgba(93,169,255,0.18), transparent 25%),
                  linear-gradient(180deg, #03050a, #0b1220 40%, #08111a 100%);
      color: var(--ink);
      font-family: "Microsoft YaHei UI", "PingFang SC", "Noto Sans SC", sans-serif;
    }
    .frame {
      position: relative;
      width: 1080px;
      height: 1920px;
      overflow: hidden;
      background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01));
    }
    .grain, .ring, .ring2 {
      position: absolute;
      inset: auto;
      border-radius: 999px;
      filter: blur(3px);
      pointer-events: none;
    }
    .grain {
      inset: 0;
      background-image:
        radial-gradient(rgba(255,255,255,0.045) 0.8px, transparent 0.8px);
      background-size: 18px 18px;
      opacity: 0.14;
      mix-blend-mode: soft-light;
    }
    .ring {
      top: -120px;
      left: -110px;
      width: 420px;
      height: 420px;
      background: radial-gradient(circle, rgba(255,141,58,0.24), rgba(255,141,58,0.02) 65%, transparent 72%);
    }
    .ring2 {
      right: -160px;
      bottom: 120px;
      width: 520px;
      height: 520px;
      background: radial-gradient(circle, rgba(93,169,255,0.18), rgba(93,169,255,0.01) 68%, transparent 76%);
    }
    .scene {
      position: absolute;
      inset: 0;
      padding: 96px 76px 236px;
      opacity: 0;
      transform: translateY(42px) scale(0.985);
      transition: opacity 320ms ease, transform 320ms ease;
      display: grid;
      align-content: start;
      gap: 28px;
    }
    .scene.visible {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
    .eyebrow {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      width: fit-content;
      padding: 10px 16px;
      border-radius: 999px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-size: 22px;
      color: #ffd6b2;
      background: rgba(255,141,58,0.14);
      border: 1px solid rgba(255,141,58,0.28);
    }
    .title {
      font-size: 94px;
      line-height: 0.96;
      font-weight: 800;
      letter-spacing: -0.04em;
      max-width: 860px;
    }
    .subtitle {
      font-size: 34px;
      line-height: 1.7;
      color: var(--muted);
      max-width: 860px;
    }
    .grid {
      display: grid;
      gap: 22px;
      grid-template-columns: 1.1fr 0.9fr;
      align-items: stretch;
    }
    .panel {
      border-radius: 34px;
      padding: 28px;
      border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.02));
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
    }
    .panel h3 {
      margin: 0 0 10px;
      font-size: 26px;
      letter-spacing: 0.08em;
      color: #ffcfaa;
      text-transform: uppercase;
    }
    .panel .body {
      font-size: 44px;
      line-height: 1.4;
    }
    .panel .small {
      margin-top: 14px;
      font-size: 28px;
      line-height: 1.65;
      color: var(--muted);
    }
    .webshot {
      width: 100%;
      height: 720px;
      object-fit: cover;
      border-radius: 30px;
      border: 1px solid rgba(255,255,255,0.1);
      box-shadow: var(--shadow);
      background: linear-gradient(160deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01));
    }
    .source-list {
      display: grid;
      gap: 14px;
    }
    .source-item {
      padding: 18px 20px;
      border-radius: 24px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.03);
    }
    .source-item strong {
      display: block;
      font-size: 26px;
      margin-bottom: 6px;
    }
    .source-item span {
      color: var(--muted);
      font-size: 24px;
      word-break: break-all;
    }
    .footer {
      position: absolute;
      left: 76px;
      right: 76px;
      bottom: 68px;
      display: flex;
      justify-content: space-between;
      color: rgba(255,255,255,0.56);
      font-size: 22px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .subbox {
      position: absolute;
      left: 70px;
      right: 70px;
      bottom: 132px;
      padding: 18px 24px;
      border-radius: 28px;
      background: rgba(3, 7, 14, 0.72);
      border: 1px solid rgba(255,255,255,0.08);
      backdrop-filter: blur(16px);
      box-shadow: 0 20px 44px rgba(0, 0, 0, 0.28);
      font-size: 42px;
      font-weight: 700;
      line-height: 1.45;
      text-align: center;
      min-height: 124px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
  </style>
</head>
<body>
  <div class="frame" id="frame">
    <div class="grain"></div>
    <div class="ring"></div>
    <div class="ring2"></div>
    <section class="scene" data-start="{{ scenes[0].start }}" data-end="{{ scenes[0].end }}">
      <div class="eyebrow">{{ payload.brand }} · {{ payload.tag }}</div>
      <div class="title">{{ payload.headline }}</div>
      <div class="subtitle">{{ payload.deck }}</div>
      <div class="panel">
        <h3>Signal</h3>
        <div class="body">{{ payload.summary }}</div>
      </div>
    </section>
    <section class="scene" data-start="{{ scenes[1].start }}" data-end="{{ scenes[1].end }}">
      <div class="eyebrow">What Happened</div>
      <div class="grid">
        <div class="panel">
          <h3>核心信息</h3>
          <div class="body">{{ payload.summary }}</div>
          <div class="small">Primary source · {{ payload.primary_domain }}</div>
        </div>
        {% if webshot_name %}
        <img class="webshot" src="{{ webshot_name }}" alt="webshot">
        {% else %}
        <div class="panel">
          <h3>Rank Score</h3>
          <div class="body">{{ payload.rank_score }}</div>
          <div class="small">这条选题来自固定热点池排序结果。</div>
        </div>
        {% endif %}
      </div>
    </section>
    <section class="scene" data-start="{{ scenes[2].start }}" data-end="{{ scenes[2].end }}">
      <div class="eyebrow">Detail A</div>
      <div class="panel">
        <h3>关键信号</h3>
        <div class="body">{{ payload.detail_a }}</div>
      </div>
    </section>
    <section class="scene" data-start="{{ scenes[3].start }}" data-end="{{ scenes[3].end }}">
      <div class="eyebrow">Detail B</div>
      <div class="panel">
        <h3>为什么重要</h3>
        <div class="body">{{ payload.detail_b }}</div>
      </div>
    </section>
    <section class="scene" data-start="{{ scenes[4].start }}" data-end="{{ scenes[4].end }}">
      <div class="eyebrow">Sources</div>
      <div class="panel">
        <h3>出处卡片</h3>
        <div class="small">{{ payload.source_text }}</div>
        <div class="source-list">
          {% for citation in payload.citations %}
          <div class="source-item">
            <strong>{{ citation.source }}</strong>
            <span>{{ citation.label }}</span>
          </div>
          {% endfor %}
        </div>
      </div>
    </section>
    <div class="subbox" id="subbox"></div>
    <div class="footer">
      <span>{{ payload.brand }}</span>
      <span>{{ payload.primary_domain }}</span>
    </div>
  </div>
  <script>
    const scenes = {{ scenes_json }};
    const cues = {{ cues_json }};
    const totalDuration = {{ total_duration }};
    const sceneNodes = [...document.querySelectorAll('.scene')];
    const subbox = document.getElementById('subbox');
    const start = performance.now();

    function tick() {
      const elapsed = Math.min(totalDuration, (performance.now() - start) / 1000);
      for (let i = 0; i < sceneNodes.length; i++) {
        const scene = sceneNodes[i];
        const meta = scenes[i];
        const active = elapsed >= meta.start && elapsed < meta.end;
        scene.classList.toggle('visible', active);
      }
      const cue = cues.find((item) => elapsed >= item.start && elapsed < item.end);
      subbox.textContent = cue ? cue.text : '';
      if (elapsed < totalDuration) {
        window.requestAnimationFrame(tick);
      }
    }
    window.requestAnimationFrame(tick);
  </script>
</body>
</html>"""
)


def format_srt_timestamp(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def split_script_sections(script: str) -> list[str]:
    return [line.strip() for line in script.splitlines() if line.strip()]


def generate_subtitle_cues(script: str, duration_seconds: float) -> list[SubtitleCue]:
    sections = split_script_sections(script)
    if not sections:
        return []
    weighted_total = sum(max(len(section), 8) for section in sections)
    cursor = 0.0
    cues: list[SubtitleCue] = []
    for index, section in enumerate(sections, start=1):
        length_weight = max(len(section), 8)
        span = duration_seconds * (length_weight / weighted_total)
        start = cursor
        cursor += span
        end = duration_seconds if index == len(sections) else cursor
        cues.append(SubtitleCue(index=index, start=round(start, 3), end=round(end, 3), text=section))
    return cues


def write_srt(cues: list[SubtitleCue], output_path: Path) -> None:
    lines = []
    for cue in cues:
        lines.append(str(cue.index))
        lines.append(f"{format_srt_timestamp(cue.start)} --> {format_srt_timestamp(cue.end)}")
        lines.append(cue.text)
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def scene_timing(total_duration: float) -> list[dict[str, float]]:
    weights = [0.18, 0.28, 0.18, 0.20, 0.16]
    cursor = 0.0
    scenes = []
    for index, weight in enumerate(weights):
        start = cursor
        cursor += total_duration * weight
        end = total_duration if index == len(weights) - 1 else cursor
        scenes.append({"start": round(start, 3), "end": round(end, 3)})
    return scenes


def capture_webshot(url: str, output_path: Path) -> bool:
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.screenshot(path=str(output_path), full_page=False)
            browser.close()
        return output_path.exists()
    except Exception:
        return False


def render_html_document(
    approved_story: ApprovedStory,
    build_dir: Path,
    total_duration: float,
    subtitle_cues: list[SubtitleCue],
    webshot_name: str | None,
) -> Path:
    scenes = scene_timing(total_duration)
    html_path = build_dir / "video.html"
    html = VIDEO_TEMPLATE.render(
        title=approved_story.title,
        payload=approved_story.scene_payload,
        scenes=scenes,
        scenes_json=json.dumps(scenes, ensure_ascii=False),
        cues_json=json.dumps([asdict(cue) for cue in subtitle_cues], ensure_ascii=False),
        total_duration=round(total_duration, 3),
        webshot_name=webshot_name,
    )
    html_path.write_text(html, encoding="utf-8")
    return html_path


def capture_cover(html_path: Path, output_path: Path, config: AppConfig) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": config.viewport_width, "height": config.viewport_height})
        page.goto(html_path.as_uri(), wait_until="load")
        page.wait_for_timeout(450)
        page.screenshot(path=str(output_path))
        browser.close()


def record_presentation(html_path: Path, output_dir: Path, config: AppConfig, duration_seconds: float) -> Path:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": config.viewport_width, "height": config.viewport_height},
            record_video_dir=str(output_dir),
            record_video_size={"width": config.viewport_width, "height": config.viewport_height},
        )
        page = context.new_page()
        page.goto(html_path.as_uri(), wait_until="load")
        page.wait_for_timeout(int((duration_seconds + 0.6) * 1000))
        video = page.video
        context.close()
        browser.close()
        recorded_path = Path(video.path())
    target_path = output_dir / "scene-video.webm"
    shutil.copy2(recorded_path, target_path)
    return target_path


def mux_video_and_audio(video_path: Path, audio_path: Path, output_path: Path, ffmpeg_path: str, fps: int) -> None:
    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        "-c:a",
        "aac",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)


def resolve_candidate(paths: ProjectPaths, story_id: str) -> StoryCandidate:
    latest = paths.latest_candidates_path
    if not latest.exists():
        raise FileNotFoundError("No candidates found. Run collect first.")
    from autohtmlvideo.storage import load_latest_candidates

    bundle = load_latest_candidates(paths)
    for candidate in bundle.candidates:
        if candidate.id == story_id:
            return candidate
    raise KeyError(f"Story ID not found in latest candidates: {story_id}")


def build_story_package(paths: ProjectPaths, config: AppConfig, story_id: str) -> Path:
    candidate = resolve_candidate(paths, story_id)
    approved_story = build_approved_story(candidate, config)
    save_approved_story(paths, approved_story)
    build_dir = paths.builds_dir / f"{story_id}-{timestamp_slug()}"
    build_dir.mkdir(parents=True, exist_ok=True)

    voice = synthesize_voice(
        text=approved_story.cn_script,
        voice_profile=config.default_voice,
        output_dir=build_dir,
        ffmpeg_path=config.ffmpeg_path,
    )
    subtitle_cues = generate_subtitle_cues(approved_story.cn_script, voice.duration_seconds)
    srt_path = build_dir / "subtitles.srt"
    write_srt(subtitle_cues, srt_path)

    webshot_path = build_dir / "webshot.png"
    has_webshot = capture_webshot(candidate.primary_url, webshot_path)
    html_path = render_html_document(
        approved_story=approved_story,
        build_dir=build_dir,
        total_duration=max(voice.duration_seconds, 20.0),
        subtitle_cues=subtitle_cues,
        webshot_name=webshot_path.name if has_webshot else None,
    )
    cover_path = build_dir / "cover.png"
    capture_cover(html_path, cover_path, config)
    video_input_path = record_presentation(
        html_path=html_path,
        output_dir=build_dir,
        config=config,
        duration_seconds=max(voice.duration_seconds, 20.0),
    )
    final_video_path = build_dir / "video.mp4"
    mux_video_and_audio(video_input_path, voice.audio_path, final_video_path, config.ffmpeg_path, config.fps)

    (build_dir / "title.txt").write_text(approved_story.title, encoding="utf-8")
    (build_dir / "description.txt").write_text(approved_story.description, encoding="utf-8")
    write_json(build_dir / "sources.json", [item.model_dump(mode="json") for item in candidate.items])
    write_json(build_dir / "approved_story.json", approved_story.model_dump(mode="json"))
    write_json(
        build_dir / "render_job.json",
        RenderJob(
            story_id=story_id,
            aspect=config.aspect,
            duration_target=config.duration_target,
            voice_profile=config.default_voice,
            theme=config.theme,
        ).model_dump(mode="json"),
    )
    write_json(
        build_dir / "build_meta.json",
        {
            "voice_provider": voice.provider_name,
            "audio_seconds": voice.duration_seconds,
            "candidate_primary_url": candidate.primary_url,
        },
    )
    return build_dir
