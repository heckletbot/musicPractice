#!/usr/bin/env python3
"""Import MusicXML and persist score data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from music_practice.score import import_musicxml, list_scores


def main() -> int:
    parser = argparse.ArgumentParser(description="Import MusicXML and persist score data")
    parser.add_argument("musicxml_path", nargs="?", help="Path to MusicXML file")
    parser.add_argument("--interval-measures", type=int, default=4, help="Measures per practice interval")
    parser.add_argument("--tempo", type=float, default=120.0, help="Default tempo if XML has no mark")
    parser.add_argument("--part-id", default=None, help="MusicXML part id (default: first part)")
    parser.add_argument("--score-id", default=None, help="Explicit score id")
    parser.add_argument("--scores-dir", default=None, help="Output directory for stored scores")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing score id")
    parser.add_argument("--list", action="store_true", help="List persisted scores")
    args = parser.parse_args()

    scores_dir = Path(args.scores_dir) if args.scores_dir else None

    if args.list:
        print(json.dumps(list_scores(scores_dir=scores_dir), ensure_ascii=False, indent=2))
        return 0

    if not args.musicxml_path:
        parser.error("musicxml_path is required unless --list is used")

    score = import_musicxml(
        args.musicxml_path,
        scores_dir=scores_dir,
        interval_measures=args.interval_measures,
        default_tempo_bpm=args.tempo,
        part_id=args.part_id,
        score_id=args.score_id,
        overwrite=args.overwrite,
    )
    print(json.dumps(score.to_summary(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
