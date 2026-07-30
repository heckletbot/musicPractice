"""Template matching engine used by start_detect (ex-music2seq).

Prefer leaf imports, e.g.::

    from music_practice.start_match.matcher.global_match import match_global_sequences
    from music_practice.start_match.template.store import load_template

Avoid ``from music_practice.start_match import *`` — package ``__init__`` stays
lightweight so locator/builder/cli are not pulled in by default.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
