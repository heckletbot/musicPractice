# 音高检测使用指南

本模块**单独使用**：音频 → 帧级音高轨 `PitchTrackData`（或内部 `PitchTrack`），不读 MusicXML、不做节奏判定。

安装：

```bash
pip install -e ".[pitch]"
# 或 pip install -e ".[audio]"
```

---

## 1. 推荐入口：`detect_pitch`

```python
from pathlib import Path
import numpy as np
from music_practice.pitch import detect_pitch, PitchDetectConfig
from music_practice.contract import (
    validate_pitch_track_data,
    dump_pitch_track_data,
    load_pitch_track_data,
    pitch_track_data_to_pitch_track,
)

# 路径
track_data = detect_pitch(
    "path/to/audio.wav",
    *,
    tempo=120.0,
    config=None,          # None → 按 tempo 选帧长
)

# 或内存 PCM（float32 mono）
pcm = np.zeros(22050, dtype=np.float32)
track_data = detect_pitch(
    pcm,
    *,
    sample_rate=22050,    # PCM 时建议显式给出
    tempo=120.0,
)

validate_pitch_track_data(track_data)
dump_pitch_track_data(track_data, "out/track.json")
```

| 项 | 说明 |
|----|------|
| **函数** | `music_practice.pitch.detect_pitch` |
| **输入** | 音频路径 **或** float32 PCM + 可选采样率 / tempo / config |
| **输出** | `PitchTrackData`：`dict[str, Any]`（已校验） |

---

## 2. 输入

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `audio` | `str` \| `Path` \| `np.ndarray` | 是 | 文件路径，或一维 `float32` mono PCM |
| `sample_rate` | `int` \| `None` | PCM 建议必填 | 目标 / PCM 采样率；默认配置为 `22050`。路径输入时按文件采样率读入并重采样到 config |
| `tempo` | `float` | 否 | 默认 `120.0`；用于 `PitchDetectConfig.for_tempo`（≥120 → 帧长 512，否则 1024） |
| `config` | `PitchDetectConfig` \| `None` | 否 | 显式配置；与 `sample_rate` 同时给出时以 `sample_rate` 覆盖采样率字段 |

### `PitchDetectConfig` 字段

```python
from music_practice.pitch import PitchDetectConfig

cfg = PitchDetectConfig(
    sample_rate=22050,
    frame_size=512,
    a4_frequency_hz=442.0,
    fmin_hz=65.0,
    fmax_hz=2093.0,
)
# window_duration_sec = frame_size / sample_rate（只读属性）
```

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `sample_rate` | `int` | `22050` | 采样率 |
| `frame_size` | `int` | `512` | 帧长（= hop） |
| `a4_frequency_hz` | `float` | `442.0` | A4 标准音 |
| `fmin_hz` / `fmax_hz` | `float` | `65` / `2093` | pyin 搜索范围 |
| `window_duration_sec` | `float` | 属性 | `frame_size / sample_rate` |

---

## 3. 输出：`PitchTrackData`

### 3.1 顶层

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `schema` | `str` | 是 | 固定 `"music_practice.pitch_track_data"` |
| `schema_version` | `str` | 是 | 当前 `"1.0"` |
| `sample_rate` | `int` | 是 | > 0 |
| `frame_size` | `int` | 是 | > 0 |
| `window_duration_sec` | `float` | 是 | > 0，通常 = `frame_size / sample_rate` |
| `frames` | `list[dict]` | 是 | 帧列表（可空，如音频短于一帧） |

### 3.2 `frames[]` 元素

| 字段 | 类型 | 说明 |
|------|------|------|
| `time_sec` | `float` | 帧起点时间（秒） |
| `frequency_hz` | `float` \| `None` | 基频；无声为 `null` |
| `pitch_midi` | `float` | MIDI；无声可为 `-1` |
| `pitch` | `str` \| `None` | 音名如 `"A4"`；无声为 `null` |
| `voiced` | `bool` | 是否有声 |

### 3.3 示例

```json
{
  "schema": "music_practice.pitch_track_data",
  "schema_version": "1.0",
  "sample_rate": 22050,
  "frame_size": 512,
  "window_duration_sec": 0.023219954648526078,
  "frames": [
    {
      "time_sec": 0.0,
      "frequency_hz": 440.0,
      "pitch_midi": 69.0,
      "pitch": "A4",
      "voiced": true
    },
    {
      "time_sec": 0.023219954648526078,
      "frequency_hz": null,
      "pitch_midi": -1.0,
      "pitch": null,
      "voiced": false
    }
  ]
}
```

---

## 4. 时段汇总（可选）

对已有轨或 WAV 某时间窗取中位音高：

```python
from music_practice.pitch import estimate_pitch, estimate_pitch_from_track
from music_practice.contract import pitch_track_data_to_pitch_track

# 路径 + 时间窗 → PitchEstimate
est = estimate_pitch("a.wav", 0.0, 0.5, tempo=120.0)

# PitchTrackData → 内部 PitchTrack 再估
track = pitch_track_data_to_pitch_track(track_data)
est = estimate_pitch_from_track(track, 0.0, 0.5)
print(est.to_dict())
```

### `PitchEstimate`（`to_dict()`）

| 字段 | 类型 | 说明 |
|------|------|------|
| `time_start_sec` | `float` | 窗起点 |
| `time_end_sec` | `float` | 窗终点 |
| `pitch_midi` | `float` | 中位 MIDI；无效为 `-1` |
| `pitch` | `str` \| `None` | 音名 |
| `frequency_hz` | `float` \| `None` | 对应频率 |
| `valid_frame_count` | `int` | 窗内有声帧数 |

---

## 5. 内部类型与桥接

| API | 说明 |
|-----|------|
| `detect_pitch_track(path, …) → PitchTrack` | 内部 dataclass，测试 / 实现用 |
| `pitch_track_from_audio(pcm, cfg) → PitchTrack` | 内存 PCM |
| `pitch_track_to_pitch_track_data(track)` | dataclass → PitchTrackData |
| `pitch_track_data_to_pitch_track(data)` | PitchTrackData → dataclass |

跨模块边界请优先传 **PitchTrackData dict**。

架构总览见 [ARCHITECTURE.md](./ARCHITECTURE.md)。
