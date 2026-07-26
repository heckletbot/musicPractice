"""Evaluate winter_1973 full template with anchored_grid; write JSON + measure table."""
from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

from music_practice.pitch.detector import detect_pitch_track
from music_practice.rhythm.config import RhythmJudgeConfig
from music_practice.rhythm.judge import ExpectedNote
from music_practice.rhythm.onset import detect_onsets
from music_practice.rhythm.pipeline import evaluate_rhythm

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/rhythm_template/winter_1973_full"
OUT_JSON = ROOT / "tests/results/rhythm_template_winter_full_anchored_grid.json"
OUT_MD = ROOT / "tests/results/winter_1973_full_by_measure_anchored_grid.md"
OUT_CSV = ROOT / "tests/results/winter_1973_full_by_measure_anchored_grid.csv"
FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def midi_bb(m: float | None) -> str:
    if m is None:
        return "?"
    mi = int(round(float(m))) + 2
    return f"{FLAT[mi % 12]}{mi // 12 - 1}"


def main() -> None:
    label = json.loads((FIXTURE / "label.json").read_text(encoding="utf-8"))
    wav = FIXTURE / label["query"]["wav"]
    tempo = float(label["tempo_bpm"])
    cut0 = float(label["template_t0_sec"]) - float(label["pre_roll_sec"])
    expected = [
        ExpectedNote(
            onset_sec=float(n["onset_sec"]),
            duration_sec=float(n["duration_sec"]),
            pitch_midi=float(n["pitch_midi"]),
            measure=int(n["measure"]),
            note_index_in_measure=int(n["note_index_in_measure"]),
        )
        for n in label["expected_notes"]
    ]
    jcfg = RhythmJudgeConfig(duration_window_mode="anchored_grid")
    print(f"evaluating {len(expected)} notes, anchored_grid, tempo={tempo}")
    segs = evaluate_rhythm(
        expected, tempo_bpm=tempo, wav_path=wav, judge_config=jcfg
    )
    onsets = detect_onsets(wav, tempo=tempo)
    track = detect_pitch_track(wav, tempo=tempo)

    rows = []
    for n, seg in zip(label["expected_notes"], segs):
        rows.append(
            {
                "note_id": n.get("note_id"),
                "measure": n["measure"],
                "note_index_in_measure": n["note_index_in_measure"],
                "onset_expected_sec": seg.onset_expected_sec,
                "onset_detected_sec": seg.onset_detected_sec,
                "onset_error_sec": seg.onset_error_sec,
                "onset_ok": seg.onset_ok,
                "duration_expected_sec": seg.duration_expected_sec,
                "duration_detected_sec": seg.duration_detected_sec,
                "duration_ratio": seg.duration_ratio,
                "duration_ok": seg.duration_ok,
                "duration_mode": seg.duration_mode,
                "rhythm_ok": seg.rhythm_ok,
                "timing_result": seg.timing_result,
            }
        )

    note_count = len(rows)
    summary = {
        "suite": "rhythm_template_winter_full_anchored_grid",
        "piece_id": label["piece_id"],
        "duration_window_mode": "anchored_grid",
        "tempo_bpm": tempo,
        "window_sec": label["window_sec"],
        "detected_onset_count": len(onsets),
        "note_count": note_count,
        "onset_ok_count": sum(1 for r in rows if r["onset_ok"]),
        "duration_ok_count": sum(1 for r in rows if r["duration_ok"]),
        "rhythm_ok_count": sum(1 for r in rows if r["rhythm_ok"]),
        "onset_ok_rate": round(sum(1 for r in rows if r["onset_ok"]) / note_count, 3),
        "duration_ok_rate": round(sum(1 for r in rows if r["duration_ok"]) / note_count, 3),
        "rhythm_ok_rate": round(sum(1 for r in rows if r["rhythm_ok"]) / note_count, 3),
        "segments": rows,
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"[anchored_grid] onset {summary['onset_ok_count']}/{note_count} "
        f"dur {summary['duration_ok_count']}/{note_count} "
        f"rhythm {summary['rhythm_ok_count']}/{note_count} ({summary['rhythm_ok_rate']})"
    )

    # Measure table (Bb written + detected abs time + actual median in pad window)
    cfg = jcfg
    by_m: OrderedDict[int, list] = OrderedDict()
    enriched = []
    for note, seg in zip(label["expected_notes"], segs):
        t0 = float(note["onset_sec"]) - cfg.grid_pre_sec(tempo)
        t1 = float(note["onset_sec"]) + float(note["duration_sec"]) + cfg.grid_post_sec(tempo)
        frames = [f for f in track.frames if t0 <= f.time_sec < t1 and f.voiced]
        if frames:
            med = float(sorted(f.pitch_midi for f in frames)[len(frames) // 2])
            act = midi_bb(med)
        else:
            med, act = None, "无声"
        det_abs = (
            None
            if seg.onset_detected_sec is None
            else cut0 + float(seg.onset_detected_sec)
        )
        row = {
            "note": note,
            "seg": seg,
            "actual_name": act,
            "actual_midi": med,
            "detected_abs": det_abs,
        }
        enriched.append(row)
        by_m.setdefault(int(note["measure"]), []).append(row)

    hit = summary["rhythm_ok_count"]
    lines = [
        "# winter_1973 全曲 · anchored_grid（降B记谱）",
        "",
        "- 模式：`anchored_grid`（标准期望时间 + 前后扩展窗 + 检出起音综合）",
        "- 音名：Bb 单簧管记谱 = 音乐会音高 + 2",
        f"- 命中：{hit}/{note_count}（{100 * hit / note_count:.1f}%）"
        f"；onset_ok={summary['onset_ok_count']}/{note_count}",
        "",
        "| 第一列：小节 · 音数 · 谱面各音（记谱） | 第二列：谱面→实际:是否识别 · 检出时间(s) |",
        "|----------------------------------------|------------------------------------------|",
    ]
    csv_lines = [
        "measure,notes_in_measure,note_id,expected_written,expected_concert_midi,"
        "detected_abs_sec,recognized,actual_written,actual_concert_midi,"
        "onset_ok,duration_ok,rhythm_ok,timing_result"
    ]
    for measure, items in by_m.items():
        names = [midi_bb(r["note"]["pitch_midi"]) for r in items]
        col1 = f"m{measure} · {len(items)}音 · {' '.join(names)}"
        parts = []
        mh = 0
        for r in items:
            exp = midi_bb(r["note"]["pitch_midi"])
            ok = "是" if r["seg"].rhythm_ok else "否"
            if r["seg"].rhythm_ok:
                mh += 1
            t = "—" if r["detected_abs"] is None else f"{r['detected_abs']:.3f}s"
            parts.append(f"{exp}→{r['actual_name']}:{ok}@{t}")
            csv_lines.append(
                ",".join(
                    [
                        str(measure),
                        str(len(items)),
                        r["note"]["note_id"],
                        exp,
                        str(r["note"]["pitch_midi"]),
                        "" if r["detected_abs"] is None else f"{r['detected_abs']:.6f}",
                        "yes" if r["seg"].rhythm_ok else "no",
                        r["actual_name"],
                        "" if r["actual_midi"] is None else f"{r['actual_midi']:.2f}",
                        str(r["seg"].onset_ok),
                        str(r["seg"].duration_ok),
                        str(r["seg"].rhythm_ok),
                        r["seg"].timing_result,
                    ]
                )
            )
        lines.append(f"| {col1} | {' · '.join(parts)} （命中 {mh}/{len(items)}） |")

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    OUT_CSV.write_text("\n".join(csv_lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")

    # Highlight m25-m28 vs previous full-detect rates if available
    prev = ROOT / "tests/results/rhythm_template_winter_full.json"
    if prev.exists():
        p = json.loads(prev.read_text(encoding="utf-8"))
        pr = p["mode_full_detect"]["rhythm_ok_rate"]
        print(f"compare previous detected_onset rhythm_ok_rate={pr} -> anchored={summary['rhythm_ok_rate']}")


if __name__ == "__main__":
    main()
