from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

START_DETECT_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "start_detect"
PLAYED_ANCHORS = Path(__file__).resolve().parent / "fixtures" / "played_anchors"

# Prefer installed music2seq; fall back to bundled deps/music2seq for editable/local runs.
_BUNDLED_M2 = ROOT / "deps" / "music2seq"
if _BUNDLED_M2.exists():
    import sys

    if str(_BUNDLED_M2) not in sys.path:
        sys.path.insert(0, str(_BUNDLED_M2))
