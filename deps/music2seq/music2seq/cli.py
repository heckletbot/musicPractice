"""Command-line interface for music2seq."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="music2seq: 模板构建与片段定位")
    sub = parser.add_subparsers(dest="command", required=True)

    build_p = sub.add_parser("build", help="从参考音频构建模板")
    build_p.add_argument("source_wav", type=Path)
    build_p.add_argument("--id", dest="template_id", default=None)
    build_p.add_argument("--templates-dir", type=Path, default=None)
    build_p.add_argument("--overwrite", action="store_true")
    build_p.add_argument("--score-path", type=Path, default=None, help="MusicXML 谱面路径，构建 note_events.json")
    build_p.add_argument(
        "--feature-kind",
        choices=("mel", "pitch"),
        default="mel",
        help="特征类型：mel 或 pitch（Chroma-CQT）",
    )
    build_p.add_argument(
        "--use-harmonic",
        action="store_true",
        help="pitch 模式下启用谐波提取（默认 pitch 预设已开启）",
    )
    build_p.add_argument(
        "--allow-short-template",
        action="store_true",
        help="跳过模板 5~30 分钟时长校验",
    )

    match_p = sub.add_parser("match", help="在模板中定位查询片段")
    match_p.add_argument("template_id")
    match_p.add_argument("query_wav", type=Path)
    match_p.add_argument("--templates-dir", type=Path, default=None)
    match_p.add_argument("--top-k", type=int, default=3)
    match_p.add_argument(
        "--search-mode",
        choices=("global", "coarse_local"),
        default="global",
        help="global=全模板无约束子序列 DTW；coarse_local=粗搜+局部 DTW",
    )
    match_p.add_argument("--json", action="store_true", dest="as_json")

    locate_p = sub.add_parser("locate", help="在模板中定位查询片段并映射到谱面音符")
    locate_p.add_argument("template_id")
    locate_p.add_argument("query_wav", type=Path)
    locate_p.add_argument("--templates-dir", type=Path, default=None)
    locate_p.add_argument("--top-k", type=int, default=5)
    locate_p.add_argument("--json", action="store_true", dest="as_json")

    convert_p = sub.add_parser("convert-m4a", help="将目录内 .m4a 批量转为 .mp3（需 ffmpeg）")
    convert_p.add_argument("input_dir", type=Path, help="含 .m4a 的目录")
    convert_p.add_argument("--output-dir", type=Path, default=None, help="输出目录，默认同 input_dir")
    convert_p.add_argument("--overwrite", action="store_true")
    convert_p.add_argument("--bitrate", type=str, default="192k")
    convert_p.add_argument("--recursive", action="store_true")

    args = parser.parse_args()

    if args.command == "build":
        from music2seq import build_template
        from music2seq.features.preprocess import pitch_preprocess_config
        from music2seq.types import FEATURE_KIND_MEL, FEATURE_KIND_PITCH

        feature_kind = FEATURE_KIND_PITCH if args.feature_kind == "pitch" else FEATURE_KIND_MEL
        preprocess = None
        if feature_kind == FEATURE_KIND_PITCH and args.use_harmonic:
            preprocess = pitch_preprocess_config()

        tid = build_template(
            args.source_wav,
            template_id=args.template_id,
            templates_dir=args.templates_dir,
            overwrite=args.overwrite,
            feature_kind=feature_kind,
            preprocess=preprocess,
            score_path=args.score_path,
            validate_duration=not args.allow_short_template,
        )
        print(tid)
        return

    if args.command == "match":
        from music2seq import match_query

        result = match_query(
            args.template_id,
            args.query_wav,
            templates_dir=args.templates_dir,
            top_k=args.top_k,
            search_mode=args.search_mode,
        )
        if args.as_json:
            print(result.to_json())
        else:
            print(f"start_sec={result.start_sec:.4f}")
            print(f"end_sec={result.end_sec:.4f}")
            print(f"score={result.score:.4f}")
            print(f"method={result.method}")
            if result.warning:
                print(f"warning={result.warning}")
        return

    if args.command == "locate":
        from music2seq import locate_query

        result = locate_query(
            args.template_id,
            args.query_wav,
            templates_dir=args.templates_dir,
            top_k=args.top_k,
        )
        if args.as_json:
            print(result.to_json())
        else:
            best = result.best
            if best is None:
                print("no_match=true")
            else:
                print(f"measure={best.measure}")
                print(f"beat={best.beat}")
                print(f"note_id={best.note_id}")
                print(f"template_sec={best.start_sec:.4f}")
                print(f"score={best.score:.4f}")
                print(f"ambiguous={str(result.ambiguous).lower()}")
                print(f"confidence={result.confidence:.4f}")
            if result.warning:
                print(f"warning={result.warning}")
        return

    if args.command == "convert-m4a":
        from music2seq.utils import convert_m4a_dir

        paths = convert_m4a_dir(
            args.input_dir,
            args.output_dir,
            overwrite=args.overwrite,
            bitrate=args.bitrate,
            recursive=args.recursive,
        )
        for p in paths:
            print(p)
        return


if __name__ == "__main__":
    main()
