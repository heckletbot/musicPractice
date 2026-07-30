# 节奏评估使用指南

本模块对「期望音符序列 + 演奏音频（或已检测 onset / 音高轨）」做逐音节奏判定。产品通过规则：**`rhythm_ok ⟺ duration_ok`**（起音 `onset_ok` 为诊断项）。

安装：

```bash
pip install -e ".[audio]"
```

推荐窗模式：`anchored_grid`（开始点锁定后的谱面期望时间轴 + 前后垫）。

---

## 1. 整体入口：`evaluate_rhythm`

```python
from music_practice.rhythm import (
    ExpectedNote,
    RhythmJudgeConfig,
    evaluate_rhythm,
)

expected = [
    ExpectedNote(onset_sec=0.0, duration_sec=0.5, pitch_midi=60, measure=1, note_index_in_measure=1),
    ExpectedNote(onset_sec=0.5, duration_sec=0.5, pitch_midi=62, measure=1, note_index_in_measure=2),
]

# 路径：自动做 onset 检测 + 音高检测，再判定
segments = evaluate_rhythm(
    expected,
    tempo_bpm=120.0,
    wav_path="path/to/play.wav",
    judge_config=RhythmJudgeConfig(duration_window_mode="anchored_grid"),
)

# 或内存 PCM
# segments = evaluate_rhythm(
#     expected,
#     tempo_bpm=120.0,
#     audio=pcm_float32,          # np.ndarray
#     sample_rate=22050,
#     judge_config=RhythmJudgeConfig(duration_window_mode="anchored_grid"),
# )

for seg in segments:
    print(seg.to_dict())
```

| 项 | 说明 |
|----|------|
| **函数** | `music_practice.rhythm.evaluate_rhythm` |
| **输出** | `list[RhythmSegment]`（与 `expected_notes` 一一对应，跳过休止逻辑后按发音音对齐） |

### 调用方式（三选一）

| 方式 | 必填参数 | 行为 |
|------|----------|------|
| A. 文件 | `wav_path` | 自动 `detect_onsets` + `detect_pitch` |
| B. PCM | `audio` + `sample_rate` | 同上，对内存缓冲 |
| C. 注入 | `detected_onsets` + `track` | 跳过检测，直接判定（测试 / 离线） |

注入示例：

```python
from music_practice.pitch import PitchTrack  # 或由 detect_pitch + bridge 得到

segments = evaluate_rhythm(
    expected,
    tempo_bpm=120.0,
    detected_onsets=[0.02, 0.51],
    track=pitch_track,   # PitchTrack
    judge_config=RhythmJudgeConfig(duration_window_mode="anchored_grid"),
)

# 等价捷径
from music_practice.rhythm import evaluate_rhythm_from_track
segments = evaluate_rhythm_from_track(
    expected, [0.02, 0.51], pitch_track,
    tempo_bpm=120.0,
    judge_config=RhythmJudgeConfig(duration_window_mode="anchored_grid"),
)
```

---

## 2. 输入数据结构

### 2.1 `ExpectedNote`

```python
from music_practice.rhythm import ExpectedNote

ExpectedNote(
    onset_sec=0.0,              # 练习时间轴起音（秒）；起点音一般为 0
    duration_sec=0.5,           # 期望时值（秒）
    pitch_midi=60.0,            # 期望 MIDI（时长窗内匹配音高用）
    measure=1,                  # 可选，写入结果 note_ref
    note_index_in_measure=1,    # 可选
    is_rest=False,              # True 则跳过分配
)
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `onset_sec` | `float` | 是 | 期望起音（练习轴，秒） |
| `duration_sec` | `float` | 是 | 期望时值（秒） |
| `pitch_midi` | `float` | 是 | 期望 MIDI |
| `measure` | `int` \| `None` | 否 | 小节号 |
| `note_index_in_measure` | `int` \| `None` | 否 | 小节内序号 |
| `is_rest` | `bool` | 否 | 默认 `false` |

`to_dict()` 输出同上字段组成的 `dict`。

**如何从 ScoreData 构造**：取 `notes` 中发音音，把练习起点 `onset` rebase 到 0（可用 `contract.slice_practice_notes`），再映射为 `ExpectedNote`。统一识别入口见 §6 `recognize`。

### 2.2 `evaluate_rhythm` 参数一览

| 名称 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `expected_notes` | `Sequence[ExpectedNote]` | — | 期望音序列 |
| `tempo_bpm` | `float` | `120.0` | 拍速；≤0 时回退 120 |
| `detected_onsets` | `Sequence[float]` \| `None` | `None` | 检出起音时刻（秒）；注入路径必填 |
| `track` | `PitchTrack` \| `None` | `None` | 音高轨；注入路径必填 |
| `audio` | `np.ndarray` \| `None` | `None` | float32 mono PCM |
| `sample_rate` | `int` \| `None` | `None` | PCM 采样率 |
| `wav_path` | `str` \| `Path` \| `None` | `None` | 音频文件 |
| `judge_config` | `RhythmJudgeConfig` \| `None` | 默认实例 | 判定阈值与窗模式 |
| `onset_config` | `OnsetDetectConfig` \| `None` | 按 tempo | onset 检测配置 |

### 2.3 `RhythmJudgeConfig`（常用字段）

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `duration_window_mode` | `str` | `"detected_onset"` | `"detected_onset"` / `"score_grid"` / `"anchored_grid"` |
| `onset_tolerance_beat` | `float` | `0.35` | 起音容差（拍） |
| `onset_tolerance_sec_cap` | `float` | `0.25` | 起音容差上限（秒） |
| `duration_pitch_tolerance_semitone` | `float` | `1.0` | 时值窗内音高容差（半音） |
| `grid_pre_beat` / `grid_post_beat` | `float` | `0.2` / `0.35` | `anchored_grid` 前后垫（拍） |
| `duration_trim_ratio` | `float` | `0.15` | 边缘裁剪比例 |

交付场景建议：

```python
RhythmJudgeConfig(duration_window_mode="anchored_grid")
```

### 2.4 `OnsetDetectConfig`（自动检测时）

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `sample_rate` | `int` | `22050` | 采样率 |
| `frame_size` | `int` | `512` | 帧长 |
| `multiplier` | `float` | `1.6` | 谱通量峰阈值倍数 |
| `min_peak_strength` | `float` | `1e-4` | 最小峰强度 |

`OnsetDetectConfig.for_tempo(tempo, sample_rate=…)` 会按 tempo 对齐帧长。

---

## 3. 输出：`RhythmSegment`

每个期望发音音一条。可用 `seg.to_dict()`：

| 字段 | 类型 | 说明 |
|------|------|------|
| `note_ref` | `dict` \| `None` | 通常含 `measure`、`note_index_in_measure` |
| `onset_expected_sec` | `float` | 期望起音 |
| `onset_detected_sec` | `float` \| `None` | 匹配到的检出起音；未匹配为 `null` |
| `onset_error_sec` | `float` \| `None` | 检出 − 期望 |
| `onset_ok` | `bool` | 起音是否在容差内（诊断） |
| `duration_expected_sec` | `float` | 期望时值 |
| `duration_detected_sec` | `float` | 测得时值 |
| `duration_ratio` | `float` \| `None` | 测得 / 期望 |
| `duration_ok` | `bool` | 时值是否通过 |
| `duration_mode` | `str` | 时值判定所用档位标签 |
| `rhythm_ok` | `bool` | **产品对错**，等于 `duration_ok` |
| `timing_result` | `str` | `"CORRECT"` / `"ONSET_ERROR"` / `"DURATION_ERROR"` / `"BOTH_ERROR"` |
| `valid_frame_count` | `int` | 时值窗内有效音高帧数 |

示例：

```python
{
  "note_ref": {"measure": 1, "note_index_in_measure": 1},
  "onset_expected_sec": 0.0,
  "onset_detected_sec": 0.02,
  "onset_error_sec": 0.02,
  "onset_ok": true,
  "duration_expected_sec": 0.5,
  "duration_detected_sec": 0.48,
  "duration_ratio": 0.96,
  "duration_ok": true,
  "duration_mode": "faster_than_quarter",
  "rhythm_ok": true,
  "timing_result": "CORRECT",
  "valid_frame_count": 18
}
```

---

## 4. 相关能力（可选）

### 4.1 仅 onset

```python
from music_practice.rhythm import detect_onsets, detect_onsets_audio

times = detect_onsets("a.wav", tempo=120.0)           # list[float]
times = detect_onsets_audio(pcm, sample_rate=22050, tempo=120.0)
```

### 4.2 空拍前后双校准

长休止后可先校正期望时间轴，再 `evaluate_rhythm`：

```python
from music_practice.rhythm import apply_rest_reanchors, RestReanchorConfig

adjusted, events = apply_rest_reanchors(
    expected,
    track,
    tempo_bpm=120.0,
    config=RestReanchorConfig(),
)
segments = evaluate_rhythm(adjusted, tempo_bpm=120.0, detected_onsets=onsets, track=track, ...)
```

### 4.3 流式会话

```python
from music_practice.rhythm import RhythmSession
# push PCM 帧 → 可能返回已关闭的 RhythmSegment；flush 收尾
```

细节见 [ARCHITECTURE.md](./ARCHITECTURE.md) §5。

---

## 5. 底层判定：`judge_notes`

在已有 onset 列表与 `PitchTrack` 时直接判定（`evaluate_rhythm` 最终调用它）：

```python
from music_practice.rhythm import judge_notes, RhythmJudgeConfig

segments = judge_notes(
    expected,
    detected_onsets,
    track,
    tempo_bpm=120.0,
    config=RhythmJudgeConfig(duration_window_mode="anchored_grid"),
)
```

| 输入 | 类型 |
|------|------|
| `expected_notes` | `Sequence[ExpectedNote]` |
| `detected_onsets` | `Sequence[float]` |
| `track` | `PitchTrack` |
| `tempo_bpm` | `float` |
| `config` | `RhythmJudgeConfig` \| `None` |

输出：`list[RhythmSegment]`。

---

## 6. 与谱面/音高一起用：`recognize`

若已有 `ScoreData` + 音频，可用统一入口（内部会做节奏 + 音高对错）：

```python
from music_practice.recognize import recognize
import numpy as np

result = recognize(
    score_data,                 # ScoreData dict
    audio.tobytes(),            # float32 PCM bytes，或直接传 ndarray
    sample_rate=22050,
    start_from={"measure": 4, "note_index": 1},   # 可选；None = 从第一个音
    config={
        "duration_window_mode": "anchored_grid",
        "pitch_tolerance_semitones": 1.0,
        "onset_tolerance_beat": 0.35,
        "onset_tolerance_sec_cap": 0.25,
    },
)
```

### `start_from`

| 字段 | 类型 | 说明 |
|------|------|------|
| `measure` | `int` | 小节号，从 1 |
| `note_index` | `int` | 小节内序号，从 1（= `note_index_in_measure`） |

### `RecognizeResult`（返回 `dict`）

| 字段 | 类型 | 说明 |
|------|------|------|
| `schema` | `str` | `"music_practice.recognize_result"` |
| `schema_version` | `str` | `"1.0"` |
| `summary` | `dict` | 见下 |
| `notes` | `list[dict]` | 逐音结果 |
| `start_from` | `dict` | 解析后的起点 `{measure, note_index}` |

**`summary`**

| 字段 | 类型 |
|------|------|
| `total_notes` | `int` |
| `correct_count` | `int` |
| `onset_error_count` | `int` |
| `duration_error_count` | `int` |
| `pitch_error_count` | `int` |
| `missed_count` | `int` |
| `accuracy` | `float` |

**`notes[]` 元素**

| 字段 | 类型 | 说明 |
|------|------|------|
| `measure` / `note_index_in_measure` | `int` \| `None` | 位置 |
| `onset_expected_sec` / `onset_detected_sec` / `onset_ok` | … | 起音 |
| `duration_expected_sec` / `duration_detected_sec` / `duration_ok` | … | 时值 |
| `pitch_expected_midi` / `pitch_detected_midi` / `pitch_ok` | … | 音高 |
| `rhythm_ok` | `bool` | 节奏对错 |
| `overall_correct` | `bool` | 音高 ∧ 节奏 ∧ 非漏音 |
| `error_dims` | `list[str]` | 如 `"onset"` / `"duration"` / `"pitch"` / `"missed"` |

离线注入：

```python
from music_practice.recognize import recognize_from_track

result = recognize_from_track(
    score_data,
    detected_onsets=[...],
    track=pitch_track_or_pitch_track_data,  # PitchTrack 或 PitchTrackData dict
    start_from={"measure": 1, "note_index": 1},
    config={"duration_window_mode": "anchored_grid"},
)
```

谱面转换见 [GUIDE_MUSICXML.md](./GUIDE_MUSICXML.md)；音高检测见 [GUIDE_PITCH.md](./GUIDE_PITCH.md)。
