"""Subsequence DTW and coarse mel search."""

from __future__ import annotations

from typing import Any, Literal

import numpy as np


def frame_cost(a: np.ndarray, b: np.ndarray, metric: Literal["l2", "cosine"] = "l2") -> float:
    if metric == "cosine":
        na = float(np.linalg.norm(a))
        nb = float(np.linalg.norm(b))
        if na < 1e-8 or nb < 1e-8:
            return 1.0
        return float(1.0 - np.dot(a, b) / (na * nb))
    return float(np.linalg.norm(a - b))


def _backtrack_start(pi: np.ndarray, pj: np.ndarray, end_i: int, end_j: int) -> int:
    i, j = end_i, end_j
    while j > 1:
        i, j = int(pi[i, j]), int(pj[i, j])
    return max(0, i - 1)


def _run_subsequence_dp(
    template: np.ndarray,
    query: np.ndarray,
    *,
    metric: Literal["l2", "cosine"],
    band_ratio: float | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int]:
    n = template.shape[0]
    m = query.shape[0]
    if m == 0 or n == 0:
        raise ValueError("template 或 query 为空")
    if m > n:
        raise ValueError(f"查询帧数({m})大于模板帧数({n})")

    slack = None if band_ratio is None else max(1, int(band_ratio * max(n, m)))
    inf = np.float64(np.inf)
    dp = np.full((n + 1, m + 1), inf, dtype=np.float64)
    pi = np.zeros((n + 1, m + 1), dtype=np.int32)
    pj = np.zeros((n + 1, m + 1), dtype=np.int32)
    dp[:, 0] = 0.0

    for j in range(1, m + 1):
        q = query[j - 1]
        if slack is None:
            i_range = range(1, n + 1)
        else:
            i_start = max(1, j - slack)
            i_end = min(n, n - (m - j) + slack)
            i_range = range(i_start, i_end + 1)
        for i in i_range:
            c = frame_cost(template[i - 1], q, metric=metric)
            candidates = [
                (dp[i - 1, j - 1], i - 1, j - 1),
                (dp[i - 1, j], i - 1, j),
                (dp[i, j - 1], i, j - 1),
            ]
            best = min(candidates, key=lambda row: row[0])
            dp[i, j] = c + best[0]
            pi[i, j] = best[1]
            pj[i, j] = best[2]

    return dp, pi, pj, n, m


def subsequence_dtw(
    template: np.ndarray,
    query: np.ndarray,
    band_ratio: float = 0.12,
) -> tuple[float, int, int]:
    """
    Subsequence DTW: align full query to a contiguous span of template.

    Returns:
        (normalized_cost, start_frame, end_frame) on template axis (0-based, inclusive).
    """
    if band_ratio <= 0:
        return subsequence_dtw_unconstrained(template, query)
    dp, pi, pj, n, m = _run_subsequence_dp(
        template,
        query,
        metric="l2",
        band_ratio=band_ratio,
    )
    best_cost = np.float64(np.inf)
    best_end = 0
    for i in range(1, n + 1):
        if dp[i, m] < best_cost:
            best_cost = dp[i, m]
            best_end = i
    best_start = _backtrack_start(pi, pj, best_end, m)
    best_end_frame = max(best_start, min(n - 1, best_end - 1))
    return float(best_cost / max(m, 1)), best_start, best_end_frame


def subsequence_dtw_unconstrained(
    template: np.ndarray,
    query: np.ndarray,
    *,
    cost_metric: Literal["l2", "cosine"] = "l2",
) -> tuple[float, int, int]:
    """Unconstrained subsequence DTW; picks lowest-cost end then backtracks."""
    cost, start, end = subsequence_dtw_global(
        template,
        query,
        cost_metric=cost_metric,
        cost_margin=0.0,
        earliest_tiebreak=False,
    )
    return cost, start, end


def subsequence_match_rigid(
    template: np.ndarray,
    query: np.ndarray,
    *,
    cost_metric: Literal["l2", "cosine"] = "l2",
    tiebreak: Literal["earliest", "min_cost", "min_cost_latest"] = "min_cost_latest",
) -> tuple[float, int, int]:
    """Subsequence match without time warping: query frame t aligns to template start+t."""
    n = template.shape[0]
    m = query.shape[0]
    if m == 0 or n == 0 or m > n:
        raise ValueError("invalid template/query lengths for rigid match")
    if n == m:
        pairs = [(0.0, 0, n - 1)]
        best_cost, best_start, best_end = _pick_global_pair(pairs, tiebreak=tiebreak)
        return 0.0, best_start, best_end

    n_starts = n - m + 1
    costs_arr = np.empty(n_starts, dtype=np.float64)
    chunk = 256
    for c0 in range(0, n_starts, chunk):
        c1 = min(n_starts, c0 + chunk)
        for i in range(c0, c1):
            tw = template[i : i + m]
            if cost_metric == "cosine":
                costs_arr[i] = sum(
                    frame_cost(tw[t], query[t], metric="cosine") for t in range(m)
                )
            else:
                costs_arr[i] = float(np.linalg.norm(tw.reshape(-1) - query.reshape(-1)))

    pairs = [(float(costs_arr[i]), i, i + m - 1) for i in range(costs_arr.shape[0])]
    best_cost, best_start, best_end = _pick_global_pair(pairs, tiebreak=tiebreak)
    return float(best_cost / max(m, 1)), best_start, best_end


def subsequence_dtw_global(
    template: np.ndarray,
    query: np.ndarray,
    *,
    cost_metric: Literal["l2", "cosine"] = "l2",
    cost_margin: float = 0.05,
    earliest_tiebreak: bool = True,
    tiebreak: Literal["earliest", "min_cost", "min_cost_latest"] | None = None,
) -> tuple[float, int, int]:
    """
    Global subsequence DTW over full template.

    tiebreak:
      - earliest: among near-minimum-cost alignments pick smallest start (first hit)
      - min_cost: pick globally lowest cost alignment
      - min_cost_latest: lowest cost; ties prefer latest start (Step1 self-crop)
    """
    if tiebreak is not None:
        mode = tiebreak
    elif earliest_tiebreak:
        mode = "earliest"
    else:
        mode = "min_cost"
    try:
        return _subsequence_dtw_global_librosa(
            template,
            query,
            cost_metric=cost_metric,
            cost_margin=cost_margin,
            tiebreak=mode,
        )
    except Exception:
        return _subsequence_dtw_global_python(
            template,
            query,
            cost_metric=cost_metric,
            cost_margin=cost_margin,
            tiebreak=mode,
        )


def _pick_global_pair(
    pairs: list[tuple[float, int, int]],
    *,
    tiebreak: Literal["earliest", "min_cost", "min_cost_latest"],
) -> tuple[float, int, int]:
    if not pairs:
        raise RuntimeError("DTW 未找到有效路径")
    if tiebreak == "earliest":
        min_start = min(p[1] for p in pairs)
        tied = [p for p in pairs if p[1] == min_start]
        tied.sort(key=lambda row: row[0])
        return tied[0]
    pairs.sort(key=lambda row: row[0])
    min_cost = pairs[0][0]
    tied = [p for p in pairs if abs(p[0] - min_cost) <= max(1e-6, min_cost * 1e-9)]
    if tiebreak == "min_cost_latest":
        return max(tied, key=lambda row: row[1])
    return tied[0]


def _subsequence_dtw_global_librosa(
    template: np.ndarray,
    query: np.ndarray,
    *,
    cost_metric: Literal["l2", "cosine"],
    cost_margin: float,
    tiebreak: Literal["earliest", "min_cost", "min_cost_latest"],
) -> tuple[float, int, int]:
    import librosa

    metric = "cosine" if cost_metric == "cosine" else "euclidean"
    dtw_cost, path = librosa.sequence.dtw(
        X=template.T,
        Y=query.T,
        subseq=True,
        metric=metric,
    )
    path = np.asarray(path)
    m = query.shape[0]
    ends = path[0, path[1] == m - 1]
    if ends.size == 0:
        ends = np.array([path[0, -1]])
    min_cost = float(np.min(dtw_cost[path[0, path[1] == m - 1], m - 1])) if ends.size else float(dtw_cost[-1, -1])
    threshold = min_cost * (1.0 + max(0.0, cost_margin)) + 1e-9

    pairs: list[tuple[float, int, int]] = []
    for end_i in np.unique(ends):
        mask = path[0] == end_i
        start_i = int(path[0, mask][0]) if np.any(mask) else int(path[0, 0])
        end_frame = int(end_i)
        cost_val = float(dtw_cost[end_i, m - 1]) if end_i < dtw_cost.shape[0] else min_cost
        if cost_val <= threshold:
            pairs.append((cost_val, start_i, end_frame))

    if not pairs:
        start_i = int(path[0, 0])
        end_i = int(path[0, -1])
        pairs = [(float(dtw_cost[end_i, m - 1]), start_i, end_i)]

    best_cost, best_start, best_end = _pick_global_pair(pairs, tiebreak=tiebreak)
    return float(best_cost / max(m, 1)), best_start, best_end


def subsequence_dtw_global_topk(
    template: np.ndarray,
    query: np.ndarray,
    *,
    top_k: int = 5,
    cost_metric: Literal["l2", "cosine"] = "l2",
    min_separation_frames: int | None = None,
) -> list[tuple[float, int, int]]:
    """Return diverse low-cost full-template subsequence DTW candidates.

    This uses the Python DP path so every possible end position is available.
    Results are normalized costs sorted ascending: ``(cost, start, end)``.
    """

    dp, pi, pj, n, m = _run_subsequence_dp(
        template,
        query,
        metric=cost_metric,
        band_ratio=None,
    )
    costs = dp[1:, m]
    order = np.argsort(costs)
    separation = min_separation_frames if min_separation_frames is not None else max(1, m // 2)
    candidates: list[tuple[float, int, int]] = []
    seen_starts: list[int] = []
    for idx in order:
        raw_cost = float(costs[int(idx)])
        if not np.isfinite(raw_cost):
            continue
        end_i = int(idx) + 1
        start_i = _backtrack_start(pi, pj, end_i, m)
        if any(abs(start_i - prev) < separation for prev in seen_starts):
            continue
        end_frame = max(start_i, min(n - 1, end_i - 1))
        candidates.append((raw_cost / max(m, 1), start_i, end_frame))
        seen_starts.append(start_i)
        if len(candidates) >= top_k:
            break
    return candidates


def _subsequence_dtw_global_python(
    template: np.ndarray,
    query: np.ndarray,
    *,
    cost_metric: Literal["l2", "cosine"],
    cost_margin: float,
    tiebreak: Literal["earliest", "min_cost", "min_cost_latest"],
) -> tuple[float, int, int]:
    dp, pi, pj, n, m = _run_subsequence_dp(
        template,
        query,
        metric=cost_metric,
        band_ratio=None,
    )
    costs = dp[1:, m]
    min_cost = float(np.min(costs))
    if not np.isfinite(min_cost):
        raise RuntimeError("DTW 未找到有效路径")

    threshold = min_cost * (1.0 + max(0.0, cost_margin)) + 1e-9
    candidate_ends = [i + 1 for i, c in enumerate(costs) if c <= threshold]
    if not candidate_ends:
        candidate_ends = [int(np.argmin(costs)) + 1]

    pairs: list[tuple[float, int, int]] = []
    for end_i in candidate_ends:
        start_i = _backtrack_start(pi, pj, end_i, m)
        end_frame = max(start_i, min(n - 1, end_i - 1))
        pairs.append((float(dp[end_i, m]), start_i, end_frame))

    best_cost, best_start, best_end = _pick_global_pair(pairs, tiebreak=tiebreak)
    return float(best_cost / max(m, 1)), best_start, best_end


def coarse_mel_candidates(
    template_mel: np.ndarray,
    query_mel: np.ndarray,
    *,
    stride: int = 8,
    top_k: int = 20,
) -> list[tuple[int, float]]:
    """Sliding cosine on flattened mel windows; return (start_frame, score)."""
    q_frames = query_mel.shape[0]
    if q_frames > template_mel.shape[0]:
        raise ValueError("查询 Mel 帧数大于模板")

    query_vec = query_mel.reshape(-1)
    q_norm = float(np.linalg.norm(query_vec)) + 1e-8
    scores: list[tuple[int, float]] = []

    last_start = template_mel.shape[0] - q_frames
    for start in range(0, last_start + 1, stride):
        window = template_mel[start : start + q_frames].reshape(-1)
        w_norm = float(np.linalg.norm(window)) + 1e-8
        score = float(np.dot(window, query_vec) / (w_norm * q_norm))
        scores.append((start, score))

    scores.sort(key=lambda row: row[1], reverse=True)
    return scores[:top_k]
