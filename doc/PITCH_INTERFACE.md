# 音高轨 ↔ 识别：固定接口约定

本文定义 **音高检测** 对外契约。识别 / 节奏模块通过固定函数消费音高轨，**不依赖检测实现细节**。

对齐模式见 [`SCORE_INTERFACE.md`](SCORE_INTERFACE.md)。

---

## 1. 职责划分

```text
┌─────────────────────┐      PitchTrackData       ┌─────────────────────┐
│  音高检测            │  ───────────────────────►  │  recognize / rhythm  │
│  detect_pitch        │         (JSON/dict)         │  只消费轨数据         │
└─────────────────────┘                             └─────────────────────┘
```

| 侧 | 做什么 | 不做什么 |
|----|--------|----------|
| **检测** | 音频 → `PitchTrackData` | 不判定节奏 / 不读 MusicXML |
| **识别** | `ScoreData` + 音频 / 轨 → 逐音判定 | 不直接依赖 pyin 等实现细节 |

---

## 2. 固定接口函数

```python
from music_practice.pitch import detect_pitch

track_data: dict = detect_pitch(
    audio,                    # 路径 str|Path，或 float32 PCM ndarray
    *,
    sample_rate=22050,        # PCM 必填；路径时可省略（按文件采样率重采样到 config）
    tempo=120.0,
    config=None,              # PitchDetectConfig；None = 按 tempo 选帧长
)
# 返回值 = PitchTrackData（见 §3）
```

契约工具（零音频依赖，仅校验 / 落盘）：

```python
from music_practice.contract import (
    PITCH_TRACK_DATA_SCHEMA,
    validate_pitch_track_data,
    dump_pitch_track_data,
    load_pitch_track_data,
    pitch_track_to_pitch_track_data,
    pitch_track_data_to_pitch_track,
)
```

内部仍保留 `detect_pitch_track` → `PitchTrack` dataclass，供实现与测试注入；**对外文档与跨模块边界以 `detect_pitch` / PitchTrackData 为准**。

`recognize_from_track(..., track=...)` 可接受 `PitchTrack` **或** PitchTrackData dict。

---

## 3. PitchTrackData

| 字段 | 类型 | 说明 |
|------|------|------|
| `schema` | str | 固定 `"music_practice.pitch_track_data"` |
| `schema_version` | str | `"1.0"` |
| `sample_rate` | int | > 0 |
| `frame_size` | int | > 0 |
| `window_duration_sec` | float | > 0（通常 = frame_size / sample_rate） |
| `frames` | list | 见下 |

### frames[]

| 字段 | 类型 | 说明 |
|------|------|------|
| `time_sec` | float | 帧起点 |
| `frequency_hz` | float \| null | 无声则为 null |
| `pitch_midi` | float | 无声可为 -1 |
| `pitch` | str \| null | 如 `"A4"` |
| `voiced` | bool | 是否有声 |

---

## 4. 安装

```bash
pip install -e ".[pitch]"   # 或 [audio]（含 pitch + 节奏/recognize）
```

默认安装不含 numpy/librosa；仅 `contract` + `score` 可用。

---

## 5. 测试

```bash
python -m pytest tests/test_pitch_track_contract.py -v
python -m pytest tests/test_recognize_decoupled.py -v   # 需 [audio]
```
