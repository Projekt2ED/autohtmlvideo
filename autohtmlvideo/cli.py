from __future__ import annotations

import argparse
import json
from pathlib import Path

from autohtmlvideo.collectors import collect_candidates
from autohtmlvideo.config import default_config
from autohtmlvideo.render import build_story_package
from autohtmlvideo.review import run_review_server
from autohtmlvideo.storage import ProjectPaths, save_candidates_bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Automated AI news short-video pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("collect", help="Collect and rank daily candidates")
    sub.add_parser("review", help="Launch local review page")
    build_parser = sub.add_parser("build", help="Build a video package from a story id")
    build_parser.add_argument("story_id", help="Candidate/story id from latest review or collect output")
    return parser


def command_collect(paths: ProjectPaths) -> int:
    config = default_config(paths.root)
    bundle = collect_candidates(config)
    archive = save_candidates_bundle(paths, bundle)
    payload = {
        "archive": str(archive),
        "candidate_count": len(bundle.candidates),
        "errors": bundle.errors,
        "candidates": [
            {
                "id": candidate.id,
                "score": candidate.rank_score,
                "title": candidate.merged_topic,
                "sources": [item.source for item in candidate.items],
            }
            for candidate in bundle.candidates
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def command_review(paths: ProjectPaths) -> int:
    if not paths.latest_candidates_path.exists():
        raise FileNotFoundError("No latest candidate bundle found. Run collect first.")
    config = default_config(paths.root)
    run_review_server(paths, host=config.review_host, port=config.review_port)
    return 0


def command_build(paths: ProjectPaths, story_id: str) -> int:
    config = default_config(paths.root)
    build_dir = build_story_package(paths=paths, config=config, story_id=story_id)
    print(json.dumps({"story_id": story_id, "build_dir": str(build_dir)}, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path.cwd().resolve()
    paths = ProjectPaths.from_root(root)
    if args.command == "collect":
        return command_collect(paths)
    if args.command == "review":
        return command_review(paths)
    if args.command == "build":
        return command_build(paths, args.story_id)
    parser.error(f"Unsupported command: {args.command}")
    return 2
