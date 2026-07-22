"""PCM audio frame for streaming start detection."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AudioFrame:
    """One PCM buffer packet from the continuous stream."""

    seq: int
    pcm: np.ndarray
    sample_rate: int = 22050
    t0_sec: float | None = None

    def __post_init__(self) -> None:
        pcm = np.asarray(self.pcm, dtype=np.float32).reshape(-1)
        object.__setattr__(self, "pcm", pcm)

    @property
    def sample_count(self) -> int:
        return int(self.pcm.shape[0])

    @property
    def duration_sec(self) -> float:
        if self.sample_rate <= 0:
            return 0.0
        return self.sample_count / float(self.sample_rate)
